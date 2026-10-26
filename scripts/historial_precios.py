"""Guarda cada día los precios online de supermercados en precios_hist.json (para los gráficos de la pestaña Alzas).

Uso: python scripts/historial_precios.py [--hoy precios_super.json] [--hist precios_hist.json] [--dias 400]

Formato: {"fechas": ["2026-10-26", ...], "cadenas": {"plazavea": {"tomate": [3.99, null, ...]}}}
Una columna por fecha (la del archivo del día). Si la fecha ya existe, se reemplaza. Se guardan los últimos N días.
"""

import argparse
import json
import pathlib


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hoy", default="precios_super.json")
    ap.add_argument("--hist", default="precios_hist.json")
    ap.add_argument("--dias", type=int, default=400)
    a = ap.parse_args(argv)

    hoy = json.loads(pathlib.Path(a.hoy).read_text(encoding="utf-8"))
    fecha = hoy.get("fecha")
    if not fecha or not isinstance(hoy.get("cadenas"), dict):
        raise SystemExit("precios del día sin fecha o sin cadenas")

    ruta = pathlib.Path(a.hist)
    hist = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {"fechas": [], "cadenas": {}}
    fechas, cadenas = hist.get("fechas", []), hist.get("cadenas", {})

    if fecha in fechas:
        i = fechas.index(fecha)
    else:
        fechas.append(fecha)
        fechas.sort()
        i = fechas.index(fecha)
        for prods in cadenas.values():                    # abrir una columna vacía en la posición de la fecha
            for serie in prods.values():
                serie.insert(i, None)

    for cid, c in hoy["cadenas"].items():
        prods = cadenas.setdefault(cid, {})
        for pid, x in (c.get("precios") or {}).items():
            serie = prods.setdefault(pid, [None] * len(fechas))
            while len(serie) < len(fechas):
                serie.append(None)
            precio = x.get("precio") if isinstance(x, dict) else None
            serie[i] = round(float(precio), 2) if precio else None

    if len(fechas) > a.dias:                              # quedarse con los últimos N días
        corte = len(fechas) - a.dias
        fechas = fechas[corte:]
        for prods in cadenas.values():
            for pid in list(prods):
                prods[pid] = prods[pid][corte:]

    ruta.write_text(json.dumps({"fechas": fechas, "cadenas": cadenas}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(fechas)} días en {a.hist} (último: {fecha})")


if __name__ == "__main__":
    main()
