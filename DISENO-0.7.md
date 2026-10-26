# Acuánto 0.7 — Platos, registro opcional, historial y pestaña Alzas

Fecha: 26 oct 2026 · Estado: aprobado por Roy (chat, 26 oct 2026, 00:40)

## Objetivo
Que la planificación semanal sea más completa (más platos, bebidas, opción fit), que la app aprenda qué cocina la gente,
que cada persona vea lo que ya compró, y que se entienda **qué está subiendo y por qué**.

## A. Platos y bebidas
- Hasta 6 elementos por día (antes 3).
- El tipo "refresco" se muestra como **Bebidas** (id interno igual, para no romper semanas guardadas) e incluye calientes.
- ~25 platos nuevos que usan los productos que la app ya cotiza (+ avena).
- **Kcal y proteína referenciales por porción**: suma de ingredientes × tabla por producto (tal como se compra, con
  merma aproximada), basada en las Tablas Peruanas de Composición de Alimentos (INS-CENAN). Nota visible: referencial.
- **Fit** = proteína ≥ 20 g, ≥ 20 % de las kcal desde proteína y ≤ 650 kcal; o marcado a mano (`fit: true`).
- **Popularidad** = puntaje base (`pop`, 0–100) + hasta 40 puntos por elecciones reales (RPC `acuanto_platos_top`,
  totales sin datos personales: elegir plato pesa 1, descargar la lista pesa 2). Insignia "Popular" (base) o
  "Más elegido" (cuando hay ≥ 10 elecciones del tipo).

## B. Registro opcional
- Paso 4 de la bienvenida, solo en la versión web (Supabase). Nombre + celular (9 dígitos, empieza en 9) + casilla de
  consentimiento obligatoria para enviar. Botón "Ahora no".
- Tabla `personas`: solo INSERT para la clave pública; sin lectura. Enlazada por `sesion`.
- Pendiente antes de abrir al público: inscribir el banco de datos ante la ANPD y publicar política de privacidad (Ley 29733).

## C. Historial
- Cada "Guardar imagen" guarda la semana (clave del lunes, días → platos, frutas, personas, total, lugar, productos).
  Una entrada por semana (la última reemplaza). Máximo 52.
- Vista "Mi historial": calendario mensual (ícono del primer plato de cada día), lista de semanas con "Usar otra vez",
  productos más comprados.
- Evento `descargar_lista` con semana, platos, total y lugar (sin datos personales).

## D. Pestaña Alzas
- INEI, IPC Lima Metropolitana: alimentos que más subieron y bajaron por mes (jun–set 2026), con fuente. Se actualiza
  a mano cada mes (el INEI publica el día 1).
- "En tu canasta": cruza tus productos con el último mes.
- "Por qué sube": El Niño costero (ENFEN), combustibles (INEI), transportistas; con fecha y fuente.
- Precio online diario por producto y supermercado: `precios_hist.json`, lo arma la tarea diaria (`scripts/historial_precios.py`).
- Gráficos: barras divergentes (rojo sube / azul baja, eje en 0) y líneas (una por cadena, leyenda + etiqueta final),
  colores validados con el validador de dataviz; tooltips y tabla alternativa.

## Fuera de alcance
Login con contraseña/SMS, lectura automática de PDFs del INEI, precios reales por mercado.

## Pruebas
Playwright: 6 platos por día, filtro fit y kcal, orden por popularidad (con RPC simulado), registro (válido, inválido,
"Ahora no", sin datos personales en eventos), historial tras descargar, pestaña Alzas sin desbordes a 360 px y letra
grande, sin errores de consola.
