"""Precios del Gran Mercado Mayorista de Lima (EMMSA): guarda los días nuevos y arma los archivos de Acuánto.

Fuente: la consulta pública de precios diarios de EMMSA (https://www.emmsa.com.pe/index.php/precios-diarios/),
la misma que usa su página. Un pedido por día nuevo, con pausa. Los 2 últimos días guardados se vuelven a pedir,
porque EMMSA puede corregirlos durante el día.

Uso: python scripts/mayorista.py [--csv precios_mayorista.csv] [--json precios_mayorista.json] [--dias 180]

- precios_mayorista.csv: todas las variedades, una fila por día y variedad (S/ por kilo: mínimo, máximo y promedio).
  Lo usa el tablero de gerencia.
- precios_mayorista.json: solo la variedad de referencia de cada producto que la app cotiza, como series por día.
  Lo usa la app (pestaña Alzas y referencia del Plan Restaurante).
"""

import argparse
import csv
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0 (compatible; AcuantoPrecios/0.1; +https://github.com/ItzElysium/acuanto)"}
EMMSA = "https://rpdiarios.emmsa.com.pe/controller/precios.php"
LIMA = timezone(timedelta(hours=-5))
# Variedad de referencia de EMMSA (código de producto, código de variedad) para cada producto de la app.
# Fija, para que la serie no salte de una variedad a otra.
REF = {
    ("30", "01"): "limon", ("48", "06"): "tomate", ("14", "02"): "cebolla", ("38", "01"): "papa-amarilla",
    ("38", "11"): "papa-blanca", ("02", "02"): "aji", ("54", "03"): "zapallo", ("18", "04"): "choclo",
    ("12", "01"): "camote", ("53", "01"): "zanahoria", ("07", "01"): "arveja", ("03", "02"): "ajo",
    ("35", "01"): "olluco", ("31", "11"): "maiz-morado",
}
COLS = ["fecha", "producto_id", "producto_emmsa", "variedad", "codpro", "coddet", "precio_min", "precio_max", "precio_prom"]


def pedir(op, data=None):
    body = urllib.parse.urlencode(data, doseq=True).encode() if data else None
    for intento in range(3):
        try:
            req = urllib.request.Request(f"{EMMSA}?op={op}", data=body, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except Exception as e:  # red o servidor: reintenta dos veces
            print(f"reintento {op}: {e}", file=sys.stderr)
            time.sleep(5)
    raise RuntimeError(f"EMMSA no respondió ({op})")


def actualizar(filas, dias, pausa):
    recientes = set(sorted({r["fecha"] for r in filas})[-2:])
    filas = [r for r in filas if r["fecha"] not in recientes]
    ya = {r["fecha"] for r in filas}
    inicio = (datetime.now(LIMA).date() - timedelta(days=dias)).isoformat()
    fechas = [f for f in pedir("listar_fechas")
              if inicio <= f["fecha"].replace("/", "-") and f["fecha"].replace("/", "-") not in ya]
    productos = [p["codpro"] for p in pedir("listar_productos")]
    nuevos = 0
    for f in sorted(fechas, key=lambda x: x["fecha"]):
        d = pedir("consultar_precios", {"anoenc": f["anoenc"], "mesenc": f["mesenc"], "numero": f["numero"], "productos[]": productos})
        if not d.get("success"):
            continue
        dia, nuevos = f["fecha"].replace("/", "-"), nuevos + 1
        for r in d.get("data") or []:
            k = (str(r["codpro"]).strip(), str(r["coddet"]).strip())
            filas.append({"fecha": dia, "producto_id": REF.get(k, ""), "producto_emmsa": str(r["producto"]).strip().title(),
                          "variedad": str(r["variedad"]).strip(), "codpro": k[0], "coddet": k[1],
                          "precio_min": float(r["precio_min"]), "precio_max": float(r["precio_max"]), "precio_prom": float(r["precio_prom"])})
        time.sleep(pausa)
    filas = [r for r in filas if r["fecha"] >= inicio]
    filas.sort(key=lambda r: (r["fecha"], r["codpro"], r["coddet"]))
    return filas, nuevos


def series_app(filas):
    fechas = sorted({r["fecha"] for r in filas})
    pos = {f: i for i, f in enumerate(fechas)}
    productos = {}
    for r in filas:
        pid = r["producto_id"]
        if not pid:
            continue
        s = productos.setdefault(pid, {"variedad": r["variedad"], "prom": [None] * len(fechas), "min": [None] * len(fechas), "max": [None] * len(fechas)})
        i = pos[r["fecha"]]
        s["prom"][i], s["min"][i], s["max"][i] = (round(float(r[k]), 2) for k in ("precio_prom", "precio_min", "precio_max"))
    return {"fecha": fechas[-1] if fechas else None, "generado": datetime.now(LIMA).isoformat(timespec="minutes"),
            "fuente": "EMMSA, Gran Mercado Mayorista de Lima", "unidad": "kilo", "fechas": fechas, "productos": productos}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", default="precios_mayorista.csv")
    ap.add_argument("--json", default="precios_mayorista.json")
    ap.add_argument("--dias", type=int, default=180)
    ap.add_argument("--pausa", type=float, default=1.5)
    a = ap.parse_args(argv)

    ruta = pathlib.Path(a.csv)
    filas = list(csv.DictReader(ruta.open(encoding="utf-8"))) if ruta.exists() else []
    filas, nuevos = actualizar(filas, a.dias, a.pausa)
    if not filas:
        raise SystemExit("EMMSA no devolvió precios")
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        for r in filas:
            w.writerow({c: r.get(c, "") for c in COLS})
    app = series_app(filas)
    pathlib.Path(a.json).write_text(json.dumps(app, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{nuevos} días pedidos · {len(app['fechas'])} días guardados (último: {app['fecha']}) · {len(app['productos'])} productos de la app")


if __name__ == "__main__":
    main()
