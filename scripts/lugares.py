"""Mercados y supermercados de Lima y Callao desde OpenStreetMap, para Acuánto.

Fuente: extracto semanal de OpenStreetMap de BBBike (https://download.bbbike.org/osm/bbbike/Lima/).
Licencia de los datos: ODbL, "© colaboradores de OpenStreetMap" (la app lo muestra).
Una sola descarga por corrida (~30 MB); no consulta APIs de búsqueda punto por punto.

Uso:
    pip install osmium shapely
    python scripts/lugares.py                       # descarga el extracto y escribe lugares.json
    python scripts/lugares.py --pbf Lima.osm.pbf    # usa un archivo ya descargado

Salida (lugares.json):
    {"fecha", "fuente", "mercados": [[id, nombre, distrito, lat, lon, area_m2]],
     "supers": [[id, cadena, nombre, distrito, lat, lon]], "distritos": {nombre: [lat, lon]}}
"""

import argparse
import datetime as dt
import json
import pathlib
import re
import unicodedata
import urllib.request

import osmium
from shapely import wkb
from shapely.geometry import Point
from shapely.strtree import STRtree

URL = "https://download.bbbike.org/osm/bbbike/Lima/Lima.osm.pbf"
AGENTE = "AcuantoLugares/1.0 (+https://github.com/ItzElysium/acuanto)"

# Cadenas que la app compara (mismos id que SUPERS en la app). Se usa la marca (brand) y, si falta, el nombre.
CADENAS = {
    "plazavea": re.compile(r"plaza\s*vea"),
    "tottus": re.compile(r"tottus"),
    "metro": re.compile(r"^(hiper\s*|super\s*|supermercados?\s+|hipermercados?\s+)?metro\b(?!polit)"),
    "wong": re.compile(r"\bwong\b"),
    "mass": re.compile(r"^(tiendas?\s+)?mass\b"),
}
NOMBRE_CADENA = {"plazavea": "Plaza Vea", "tottus": "Tottus", "metro": "Metro", "wong": "Wong", "mass": "Mass"}
# Acuánto compara comida: fuera supermercados, tiendas, galerías de ropa, malls y mercados de pulgas.
NO_MERCADO = re.compile(r"super ?mercado|hipermercado|mini ?market|mini ?mercado|micro ?mercado|mercado libre|bodega|market\b|tambo|oxxo"
                        r"|^mercado de (valores|capitales)|pulgas|artesan|libro|ropa|calzado|zapat|sandalia|repuesto|autoparte|mueble|electr"
                        r"|gamarra|polvos|malvinas|cachina|importaci|bazar|tienda|abarrotes|colegio|metrito|economax")
ES_MERCADO = re.compile(r"\b(mercado|mercadillo|mercadito|abastos?|productores|mayorista|minorista|terminal pesquero|pesca terminal|bioferia)\b")
NO_ES_COMIDA = re.compile(r"centro comercial|\bc\.? ?c\.?\b|commercial|galer[ií]a|\bplaza\b|\bmall\b|center|centro|megacentro|multicentro|boulevard"
                          r"|domain|inka|kaypi|feria comercial|^\d+$|zona rigida|pyme|campo ferial")
# Nombres de distrito como los dice la gente
DISTRITO_COMUN = {"Lima": "Cercado de Lima", "Lurigancho": "Lurigancho-Chosica", "Carmen de La Legua-Reynoso": "Carmen de la Legua"}


def norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def limpiar_nombre(n):
    n = re.sub(r"\s*\([^)]*\)", "", n or "")                       # sin paréntesis: confunden en la app
    n = re.sub(r"\s+", " ", n).strip(" -·,\"'")
    if n.isupper() and len(n) > 4:
        n = n.title()
    n = re.sub(r"^(Mecado|Marcado|Gran marcado)\b", lambda m: "Gran Mercado" if m.group(0).startswith("Gran") else "Mercado", n, flags=re.I)
    n = re.sub(r"\bN(ro|°|º|o)?\.?\s*(?=\d)", "N.° ", n)
    # "Asociación de Comerciantes del Mercado X" -> "Mercado X"
    m = re.search(r"\bmercado\b", n, flags=re.I)
    if m and m.start() > 0 and re.match(r"^(asoc|asociaci|cooperativa|ac\b|a\.c\.)", n, flags=re.I):
        n = n[m.start():]
    n = n[0].upper() + n[1:] if n else n
    return n[:70]


def nombre_mercado(nombre):
    """Nombre limpio si es un mercado de comida; None si no lo es."""
    n = limpiar_nombre(nombre)
    k = norm(n)
    if not n or NO_MERCADO.search(k):
        return None
    if ES_MERCADO.search(k):
        return n
    if NO_ES_COMIDA.search(k):
        return None
    if re.match(r"^(asoc|asociaci|cooperativa)", k):
        return n
    return "Mercado " + n                                           # plaza de mercado sin la palabra "mercado"


def nombre_sede(tags, cadena):
    """Cómo distinguir la tienda: sucursal, lo que el nombre agrega a la marca, o la calle."""
    marca = NOMBRE_CADENA[cadena]
    for k in ("branch", "name"):
        v = limpiar_nombre(tags.get(k, ""))
        v = re.sub(r"(?i)^(hiper|super)?\s*(tiendas?\s+)?(plaza\s*vea|tottus|metro|wong|mass)\b(\s+(express|super|hiper))?", "", v).strip(" -·,")
        if v and norm(v) not in ("", "express", "super", "hiper"):
            return v
    calle = limpiar_nombre(tags.get("addr:street", ""))
    return calle or ""


class Lector(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.wkb = osmium.geom.WKBFactory()
        self.mercados, self.supers, self.distritos = [], [], []

    def _clasificar(self, tags):
        nombre = tags.get("name", "")
        n = norm(nombre)
        brand = norm(tags.get("brand", ""))
        shop, amenity = tags.get("shop"), tags.get("amenity")
        if shop in ("supermarket", "convenience", "department_store", "wholesale") or amenity == "marketplace":
            for cid, rx in CADENAS.items():
                if rx.search(brand) or rx.search(n):
                    if cid == "mass" and shop not in ("supermarket", "convenience"):
                        continue
                    return ("super", cid)
        if not nombre:
            return None
        if amenity == "marketplace" and not NO_MERCADO.search(n):
            return ("mercado", None)
        if re.match(r"^(mercado|mercadillo|mercadito|centro de abastos|paradero mercado)\b", n) and not NO_MERCADO.search(n) \
                and (tags.get("building") or shop or tags.get("landuse") == "retail" or amenity):
            return ("mercado", None)
        return None

    def _guardar(self, tipo, cid, tags, lat, lon, oid, area=0.0):
        fila = {"id": oid, "lat": lat, "lon": lon, "area": area, "plaza": tags.get("amenity") == "marketplace"}
        if tipo == "super":
            fila["cadena"] = cid
            fila["nombre"] = NOMBRE_CADENA[cid]
            fila["sede"] = nombre_sede(tags, cid)
            self.supers.append(fila)
        else:
            fila["nombre"] = nombre_mercado(tags.get("name", ""))
            if fila["nombre"]:
                self.mercados.append(fila)

    def node(self, n):
        if not n.tags:
            return
        c = self._clasificar(n.tags)
        if c:
            self._guardar(c[0], c[1], dict(n.tags), n.location.lat, n.location.lon, f"n{n.id}")

    def area(self, a):
        tags = a.tags
        es_distrito = tags.get("boundary") == "administrative" and tags.get("admin_level") == "8" and tags.get("name")
        c = None if es_distrito else self._clasificar(tags)
        if not (c or es_distrito):
            return
        try:
            g = wkb.loads(self.wkb.create_multipolygon(a), hex=True)
        except Exception:
            return
        if es_distrito:
            self.distritos.append((tags.get("name"), g))
            return
        p = g.representative_point()
        oid = ("w" if a.from_way() else "r") + str(a.orig_id())
        self._guardar(c[0], c[1], dict(tags), p.y, p.x, oid, g.area)


def distancia_m(a, b):
    from math import asin, cos, radians, sin, sqrt
    la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * asin(sqrt(h))


def area_m2(f):
    """Área aproximada en m² (sirve para poner primero los mercados grandes del distrito). 0 si es un punto."""
    from math import cos, radians
    return int(round(f["area"] * 111320 ** 2 * cos(radians(f["lat"])), -1))


def deduplicar(filas, clave, radio):
    """Quita repetidos: mismo nombre (o misma cadena) a menos de `radio` metros. Gana el área más grande."""
    filas = sorted(filas, key=lambda f: (-f["area"], not f["plaza"]))
    out = []
    for f in filas:
        if any(clave(f) == clave(g) and distancia_m((f["lat"], f["lon"]), (g["lat"], g["lon"])) < radio for g in out):
            continue
        out.append(f)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pbf", help="extracto .osm.pbf ya descargado")
    ap.add_argument("--salida", default="lugares.json")
    a = ap.parse_args(argv)

    lima = dt.timezone(dt.timedelta(hours=-5))
    pbf, fecha = a.pbf, None
    if not pbf:
        pbf = "Lima.osm.pbf"
        req = urllib.request.Request(URL, headers={"User-Agent": AGENTE})
        with urllib.request.urlopen(req, timeout=300) as r, open(pbf, "wb") as f:
            f.write(r.read())
            mod = r.headers.get("Last-Modified")       # fecha del extracto de BBBike
            if mod:
                from email.utils import parsedate_to_datetime
                fecha = parsedate_to_datetime(mod).astimezone(lima).date().isoformat()
    fecha = fecha or dt.datetime.fromtimestamp(pathlib.Path(pbf).stat().st_mtime, lima).date().isoformat()

    lec = Lector()
    lec.apply_file(pbf, locations=True)

    # Distrito de cada punto: el polígono que lo contiene (si hay dos, el más chico).
    polis = [g for _, g in lec.distritos]
    nombres = [n for n, _ in lec.distritos]
    arbol = STRtree(polis)

    def distrito(lat, lon):
        pt = Point(lon, lat)
        cand = [i for i in arbol.query(pt) if polis[i].contains(pt)]
        n = nombres[min(cand, key=lambda i: polis[i].area)] if cand else ""
        return DISTRITO_COMUN.get(n, n)

    mercados = deduplicar(lec.mercados, lambda f: norm(f["nombre"]), 300)
    supers = deduplicar(lec.supers, lambda f: f["cadena"], 120)
    for f in mercados + supers:
        f["distrito"] = distrito(f["lat"], f["lon"])
    mercados = [f for f in mercados if f["distrito"]]
    supers = [f for f in supers if f["distrito"]]

    usados = {f["distrito"] for f in mercados + supers}
    centros = {}
    for n, g in lec.distritos:
        n = DISTRITO_COMUN.get(n, n)
        if n in usados and n not in centros:
            p = g.representative_point()
            centros[n] = [round(p.y, 4), round(p.x, 4)]

    datos = {
        "fecha": fecha,
        "fuente": "© colaboradores de OpenStreetMap (ODbL), extracto de BBBike",
        "mercados": sorted([[f["id"], f["nombre"], f["distrito"], round(f["lat"], 5), round(f["lon"], 5), area_m2(f)] for f in mercados], key=lambda x: (x[2], x[1])),
        "supers": sorted([[f["id"], f["cadena"], f["sede"], f["distrito"], round(f["lat"], 5), round(f["lon"], 5)] for f in supers], key=lambda x: (x[1], x[3])),
        "distritos": dict(sorted(centros.items())),
    }
    pathlib.Path(a.salida).write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    por_cadena = {c: sum(1 for s in datos["supers"] if s[1] == c) for c in CADENAS}
    print(f"{len(datos['mercados'])} mercados, {len(datos['supers'])} supermercados {por_cadena}, {len(centros)} distritos -> {a.salida}")


if __name__ == "__main__":
    main()
