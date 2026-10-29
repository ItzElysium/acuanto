# Acuánto 0.9 — Quién come y qué cambió esta semana

Fecha: 29 oct 2026 · Pedido por Roy: porciones según quién come (adulto o niño), plato "bien servido" y alertas semanales del mercado mayorista.

| # | Mejora | Dónde | Cómo funciona |
|---|---|---|---|
| 1 | ¿Quiénes comen en casa? | Mi semana → primer paso | Contadores por edad. Cada grupo come una parte de la porción de un adulto: adultos 1, adultos mayores 0.85, jóvenes de 12 a 17 años 1.1, niños de 6 a 11 años 0.75, niños de 2 a 5 años 0.5. La lista y los costos usan esas "porciones de adulto". Las frutas se cuentan por persona. Las semanas guardadas antes pasan como adultos. |
| 2 | Bien servido | Mi semana → "¿Cómo sirves?" | 30% más de arroz, papa, fideos, camote y choclo, y 10% más del resto. La porción normal es el plato casero de un adulto (100 g de arroz crudo en el segundo). |
| 3 | Esta semana en el mercado mayorista | Alzas, primera tarjeta | Promedio de los últimos 7 días frente a los 7 anteriores en el Gran Mercado Mayorista de Lima (EMMSA). Muestra lo que sube o baja 10% o más, con su precio por kilo y un botón para ver qué usar en su lugar. |
| 4 | Conviene / Mejor otra semana con datos semanales | Mi semana y "Llenar días vacíos" | El cambio semanal del mayorista manda sobre el mensual del INEI; si esta semana un producto está estable, ya no se marca por el dato del mes. |
| 5 | Robot en Node 24 | `.github/workflows/publicar.yml` | checkout v5, setup-python v6, configure-pages v6, upload-pages-artifact v5 y deploy-pages v5. |

Factores por edad: referenciales, a partir de los requerimientos de energía por edad (INS-CENAN y FAO/OMS). Pendiente: validar porciones con cocineras de menú y con una nutricionista.
