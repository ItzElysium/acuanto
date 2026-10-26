"""Precios online de supermercados (catálogo público VTEX) para la canasta de Acuánto.

Uso responsable:
  - Lee el robots.txt de cada cadena antes de consultar y omite lo que esté bloqueado.
  - Una búsqueda por producto, con pausa entre pedidos; pensado para correr una vez al día.
  - Guarda solo precio público, nombre del producto y enlace. No toca cuentas ni carritos.

Funciona como parte de GeoLeads (`python -m geoleads super-precios`) o suelto, sin el resto del paquete:
  python supermercados.py --config supermercados.yaml --salida precios_super.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

USER_AGENT = "Mozilla/5.0 (compatible; AcuantoPrecios/0.1; +https://github.com/ItzElysium/acuanto)"
RUTA_BUSQUEDA = "/api/catalog_system/pub/products/search"
LIMA = timezone(timedelta(hours=-5))


# ------------------------------------------------------------------ texto y tamaños

def norm(texto: Any) -> str:
    """Minúsculas, sin tildes y con espacios simples."""
    t = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t.lower()).strip()


_NUM = r"(\d+(?:[.,]\d+)?)"
_PESO = re.compile(_NUM + r"\s*(kg|kilos?|g|gr|grs|gramos)\b")
_VOLUMEN = re.compile(_NUM + r"\s*(l|lt|lts|litros?|ml)\b")
_CUENTA = [
    re.compile(r"(?:pack|paquete|six pack|caja|bolsa)\s*(?:x|de)?\s*(\d+)\s*(?:un|und|unid|unidades|latas?|huevos?)?\b"),
    re.compile(r"\bx\s*(\d+)\s*(?:un|und|unid|unidades|latas?|huevos?)\b"),
    re.compile(r"\b(\d+)\s*(?:un|und|unid|unidades|latas|huevos)\b"),
]
_POR_KG = re.compile(r"\bx\s*kg\b|\bpor kilo\b|\b\(kg\)")


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def peso_kg(nombre: str) -> float | None:
    m = _PESO.search(norm(nombre))
    if not m:
        return None
    n, u = _num(m.group(1)), m.group(2)
    return n if u.startswith("k") else n / 1000


def volumen_l(nombre: str) -> float | None:
    m = _VOLUMEN.search(norm(nombre))
    if not m:
        return None
    n, u = _num(m.group(1)), m.group(2)
    return n / 1000 if u == "ml" else n


def cuenta(nombre: str) -> int | None:
    t = norm(nombre)
    for rx in _CUENTA:
        m = rx.search(t)
        if m and 0 < int(m.group(1)) <= 360:
            return int(m.group(1))
    return None


def precio_por_unidad(item: dict, regla: dict) -> float | None:
    """Convierte el precio del producto a S/ por la unidad de Acuánto (kilo, litro, lata o unidad)."""
    precio, nombre, med = item["precio"], item["nombre"], (item.get("medida") or "").lower()
    destino, kg_u = regla.get("unidad", "kilo"), regla.get("kg_por_unidad")
    por_kg = bool(_POR_KG.search(norm(nombre))) or med == "kg"
    if destino == "kilo":
        if por_kg:
            return precio                      # "Limón Ácido x kg": el precio publicado es por kilo
        kg = peso_kg(nombre)
        if kg:
            return precio / kg
        n = cuenta(nombre)
        if n and kg_u:
            return precio / (n * kg_u)         # "Huevos Pardos 15un" → kilos aproximados
        if kg_u and re.search(r"\bunidad\b|\bx un\b|\b1 ?un\b", norm(nombre)):
            return precio / kg_u
        return None
    if destino == "litro":
        litros = volumen_l(nombre)
        return precio / litros if litros else None
    if destino == "lata":
        n = cuenta(nombre) or (1 if "lata" in norm(nombre) else None)
        return precio / n if n else None
    if destino == "unidad":
        if por_kg and kg_u:
            return precio * kg_u               # choclo vendido por kilo → precio de un choclo
        n = cuenta(nombre) or 1
        return precio / n
    return None


# ------------------------------------------------------------------ lectura del catálogo VTEX

@dataclass
class Item:
    nombre: str
    marca: str
    categorias: list[str]
    url: str
    medida: str
    multiplicador: float
    precio: float
    precio_lista: float
    stock: int


def items_vtex(respuesta: Iterable[dict]) -> list[Item]:
    """Aplana la respuesta de /api/catalog_system/pub/products/search en un ítem por SKU con precio."""
    out: list[Item] = []
    for prod in respuesta or []:
        for sku in prod.get("items") or []:
            for vendedor in sku.get("sellers") or []:
                oferta = vendedor.get("commertialOffer") or {}
                precio = oferta.get("Price")
                if not precio or precio <= 0:
                    continue
                out.append(Item(
                    nombre=sku.get("nameComplete") or prod.get("productName") or "",
                    marca=prod.get("brand") or "",
                    categorias=list(prod.get("categories") or []),
                    url=prod.get("link") or "",
                    medida=sku.get("measurementUnit") or "",
                    multiplicador=float(sku.get("unitMultiplier") or 1),
                    precio=float(precio),
                    precio_lista=float(oferta.get("ListPrice") or precio),
                    stock=int(oferta.get("AvailableQuantity") or 0),
                ))
                break  # el primer vendedor con precio es la tienda
    return out


@dataclass
class Resultado:
    producto: str
    unidad: str
    precio: float | None = None
    mediana: float | None = None
    item: str = ""
    url: str = ""
    oferta: bool = False
    candidatos: int = 0
    descartados: dict[str, int] = field(default_factory=dict)


def elegir(producto: str, regla: dict, items: list[Item]) -> Resultado:
    """Filtra por categoría, nombre, stock y rango; se queda con el precio por unidad más bajo."""
    res = Resultado(producto=producto, unidad=regla.get("unidad", "kilo"))
    inc = re.compile(regla["incluir"]) if regla.get("incluir") else None
    exc = re.compile(regla["excluir"]) if regla.get("excluir") else None
    cats = [norm(c) for c in regla.get("categoria", [])]
    lo, hi = regla.get("rango", [0, 10**6])
    validos: list[tuple[float, Item]] = []
    motivo = lambda m: res.descartados.__setitem__(m, res.descartados.get(m, 0) + 1)  # noqa: E731
    for it in items:
        n = norm(it.nombre)
        if it.stock <= 0:
            motivo("sin_stock"); continue
        if cats and not any(c in norm(" ".join(it.categorias)) for c in cats):
            motivo("categoria"); continue
        if inc and not inc.search(n):
            motivo("nombre"); continue
        if exc and exc.search(n):
            motivo("excluido"); continue
        pu = precio_por_unidad(asdict(it), regla)
        if pu is None:
            motivo("sin_tamano"); continue
        if not lo <= pu <= hi:
            motivo("fuera_de_rango"); continue
        validos.append((round(pu, 2), it))
    res.candidatos = len(validos)
    if validos:
        validos.sort(key=lambda x: x[0])
        pu, it = validos[0]
        res.precio, res.item, res.url = pu, it.nombre, it.url
        res.oferta = it.precio < it.precio_lista - 0.009
        res.mediana = round(statistics.median(v for v, _ in validos), 2)
    return res


# ------------------------------------------------------------------ red (con robots.txt y pausas)

class Cliente:
    def __init__(self, pausa: float = 2.5, timeout: float = 20, cache_dir: Path | None = None,
                 desde_cache: Path | None = None, abrir: Callable[..., Any] | None = None, log: Callable[[str], None] = print):
        self.pausa, self.timeout, self.cache_dir, self.desde_cache = pausa, timeout, cache_dir, desde_cache
        self._abrir = abrir or urllib.request.urlopen
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._ultimo = 0.0
        self.log = log

    def _get(self, url: str) -> bytes:
        espera = self.pausa + random.uniform(0, self.pausa / 2) - (time.monotonic() - self._ultimo)
        if espera > 0 and self._ultimo:
            time.sleep(espera)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with self._abrir(req, timeout=self.timeout) as r:
                return r.read()
        finally:
            self._ultimo = time.monotonic()

    def permitido(self, base: str, ruta: str) -> bool:
        if self.desde_cache:
            return True
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                rp.parse(self._get(base.rstrip("/") + "/robots.txt").decode("utf-8", "ignore").splitlines())
                self._robots[base] = rp
            except Exception as exc:  # sin robots.txt legible: por prudencia no se consulta
                self.log(f"  ! No se pudo leer robots.txt de {base} ({exc}); se omite la cadena.")
                self._robots[base] = None
        rp = self._robots[base]
        return bool(rp and rp.can_fetch(USER_AGENT, base.rstrip("/") + ruta))

    def buscar(self, cadena: str, base: str, texto: str, maximo: int = 30) -> list[dict]:
        clave = re.sub(r"[^a-z0-9]+", "-", norm(texto)).strip("-")
        if self.desde_cache:
            f = self.desde_cache / f"{cadena}__{clave}.json"
            return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        q = urllib.parse.urlencode({"ft": texto, "_from": 0, "_to": maximo - 1})
        datos = json.loads(self._get(f"{base.rstrip('/')}{RUTA_BUSQUEDA}?{q}").decode("utf-8"))
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{cadena}__{clave}.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        return datos


def recolectar(config: dict, cadenas: list[str] | None = None, productos: list[str] | None = None,
               cliente: Cliente | None = None, log: Callable[[str], None] = print) -> dict:
    """Corre la canasta en cada cadena y devuelve el JSON que lee Acuánto."""
    cliente = cliente or Cliente(log=log)
    canasta = {k: v for k, v in config["canasta"].items() if not productos or k in productos}
    hoy = datetime.now(LIMA).date().isoformat()
    salida: dict[str, Any] = {"fecha": hoy, "generado": datetime.now(LIMA).isoformat(timespec="minutes"),
                              "fuente": "Catálogo online público de cada supermercado (VTEX)", "cadenas": {}}
    for cid, cad in config["cadenas"].items():
        if cadenas and cid not in cadenas:
            continue
        if cad.get("plataforma") != "vtex":
            log(f"- {cad['nombre']}: plataforma {cad.get('plataforma')} aún no soportada; se omite.")
            continue
        if not cliente.permitido(cad["base"], RUTA_BUSQUEDA):
            log(f"- {cad['nombre']}: robots.txt no permite consultar el catálogo; se omite.")
            continue
        log(f"- {cad['nombre']}: {len(canasta)} productos")
        precios, faltan = {}, []
        for pid, regla in canasta.items():
            try:
                items = items_vtex(cliente.buscar(cid, cad["base"], regla["buscar"]))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                log(f"    {pid}: error de consulta ({exc}); se sigue con el siguiente")
                faltan.append(pid); continue
            r = elegir(pid, regla, items)
            if r.precio is None:
                faltan.append(pid); continue
            precios[pid] = {"precio": r.precio, "unidad": r.unidad, "mediana": r.mediana, "item": r.item, "url": r.url,
                            "oferta": r.oferta, "candidatos": r.candidatos}
        salida["cadenas"][cid] = {"nombre": cad["nombre"], "precios": precios, "sin_precio": faltan}
        log(f"    con precio: {len(precios)} · sin precio: {len(faltan)}")
    return salida


def guardar_db(conn, datos: dict) -> int:
    """Guarda en la tabla precios_super de GeoLeads (una fila por fecha, cadena y producto)."""
    filas = [(datos["fecha"], cid, pid, p["precio"], p["unidad"], p.get("mediana"), p.get("item"), p.get("url"),
              int(bool(p.get("oferta"))), p.get("candidatos"))
             for cid, c in datos["cadenas"].items() for pid, p in c["precios"].items()]
    conn.executemany(
        "INSERT OR REPLACE INTO precios_super (fecha, cadena, producto, precio, unidad, mediana, item, url, oferta, candidatos) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)", filas)
    conn.commit()
    return len(filas)


# ------------------------------------------------------------------ uso suelto

def _cargar_config(path: Path) -> dict:
    texto = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(texto)
    import yaml  # solo hace falta para .yaml

    return yaml.safe_load(texto)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Precios online de supermercados para Acuánto")
    ap.add_argument("--config", type=Path, default=Path(__file__).with_name("supermercados.yaml"))
    ap.add_argument("--salida", type=Path, default=Path("precios_super.json"))
    ap.add_argument("--cadenas", help="plazavea,metro,wong (por defecto todas)")
    ap.add_argument("--productos", help="limon,tomate,… (por defecto toda la canasta)")
    ap.add_argument("--pausa", type=float, default=2.5, help="segundos entre pedidos (mínimo 1)")
    ap.add_argument("--cache", type=Path, help="guarda las respuestas crudas en esta carpeta")
    ap.add_argument("--desde-cache", type=Path, help="no usa internet: lee respuestas guardadas")
    a = ap.parse_args(argv)
    cli = Cliente(pausa=max(1.0, a.pausa), cache_dir=a.cache, desde_cache=a.desde_cache)
    datos = recolectar(_cargar_config(a.config), a.cadenas.split(",") if a.cadenas else None,
                       a.productos.split(",") if a.productos else None, cli)
    a.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(c["precios"]) for c in datos["cadenas"].values())
    print(f"Listo: {total} precios en {a.salida}")
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
