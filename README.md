# Acuánto · versión de prueba

App web para planificar la compra de la semana en Lima:

- **Precios del día** en mercados y supermercados cercanos.
- **Mi semana**: eliges el plato de cada día (lunes a domingo) y para cuántas personas. La app arma la canasta, te dice cuánto cuesta y dónde sale más barato.
- **Plan Restaurante** (premium, gratis en la prueba): costo de insumos por menú, pedido para tus proveedores y control de precios del proveedor.
- Botón **💬 Opinar** para dejar ideas.

> Prototipo. Los precios de mercados son de ejemplo. Los de supermercados se actualizan cada mañana desde su tienda online, si la tienda responde; si no, también son de ejemplo.

## Cómo está armado

| Archivo | Qué hace |
|---|---|
| `index.html` | La app completa (un solo archivo) |
| `manifest.webmanifest`, `sw.js`, `icon-*.png` | Para instalarla en el celular y abrirla sin señal |
| `og.png` | Imagen que muestra WhatsApp al compartir el link |
| `scripts/supermercados.py` + `scripts/supermercados.yaml` | Lee el catálogo online público de Plaza Vea, Metro y Wong y deja `precios_super.json` (S/ por kilo, litro, lata o unidad) |
| `scripts/mayorista.py` | Guarda el precio del día del Gran Mercado Mayorista de Lima (consulta pública de EMMSA): `precios_mayorista.csv` con todas las variedades (tablero de gerencia) y `precios_mayorista.json` con la variedad de referencia de cada producto (gráfico de Alzas y referencia del Plan Restaurante) |
| `.github/workflows/publicar.yml` | Publica la página y, cada día a las 6:30 a. m., actualiza los precios |

## Uso responsable de datos

- El recolector lee el `robots.txt` de cada tienda y no consulta lo bloqueado. Hace una búsqueda por producto, con pausa, una vez al día.
- Los precios mayoristas salen de la consulta pública de EMMSA: un pedido por día nuevo, con pausa.
- Solo guarda el precio público, el nombre del producto y el enlace.
- Las opiniones de la app no piden nombre.

## Cambiar a quién llegan las opiniones

En `index.html`, busca `WHATSAPP_OPINIONES = ""` y pon tu número con código de país, por ejemplo `"51999888777"`. Ese número quedará público en el repositorio.
