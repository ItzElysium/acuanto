-- =====================================================================
-- Acuánto · base de datos de la prueba (Supabase / Postgres)
-- Qué guarda: uso anónimo de la app, aportes de precios, opiniones e
-- historial de precios de supermercados.
-- Seguridad: la app (clave pública) solo puede INSERTAR; nadie puede leer
-- las filas desde afuera. Para ver los datos: panel de Supabase o la
-- función acuanto_resumen(), que devuelve solo totales agregados.
-- Sin nombres ni teléfonos: cada celular tiene un identificador al azar.
-- =====================================================================

-- 1) Uso de la app: una fila por acción (abrir, elegir plato, ver canasta…)
create table if not exists public.eventos (
  id        bigint generated always as identity primary key,
  ts        timestamptz not null default now(),
  sesion    text not null check (char_length(sesion) between 8 and 64),
  version   text check (char_length(version) <= 20),
  rol       text check (rol in ('compra', 'puesto', 'resto') or rol is null),
  evento    text not null check (char_length(evento) between 2 and 40),
  datos     jsonb not null default '{}'::jsonb check (pg_column_size(datos) <= 2000)
);
create index if not exists eventos_ts on public.eventos (ts);
create index if not exists eventos_evento on public.eventos (evento, ts);

-- 2) Aportes de precios desde la app (pizarra, escrito, "no hay", puesto, proveedor)
create table if not exists public.aportes (
  id        bigint generated always as identity primary key,
  ts        timestamptz not null default now(),
  sesion    text not null check (char_length(sesion) between 8 and 64),
  mercado   text check (char_length(mercado) <= 60),
  producto  text check (char_length(producto) <= 40),
  libre     text check (char_length(libre) <= 40),
  precio    numeric(8,2) check (precio is null or precio between 0 and 1000),
  unidad    text check (char_length(unidad) <= 20),
  fuente    text check (fuente in ('foto', 'manual', 'nohay', 'puesto', 'confirmacion', 'proveedor'))
);
create index if not exists aportes_prod on public.aportes (producto, ts);

-- 3) Opiniones del botón "Opinar"
create table if not exists public.opiniones (
  id         bigint generated always as identity primary key,
  ts         timestamptz not null default now(),
  sesion     text not null check (char_length(sesion) between 8 and 64),
  version    text check (char_length(version) <= 20),
  rol        text check (char_length(rol) <= 10),
  nota       text check (nota in ('mal', 'bien', 'super') or nota is null),
  util       text[] check (cardinality(util) <= 10),
  frecuencia text check (char_length(frecuencia) <= 10),
  pago       text check (char_length(pago) <= 20),
  texto      text check (char_length(texto) <= 1000)
);

-- 4) Historial de precios online de supermercados (lo llena la tarea diaria de GitHub)
create table if not exists public.precios_super_hist (
  fecha      date not null,
  cadena     text not null,
  producto   text not null,
  precio     numeric(8,2),
  unidad     text,
  mediana    numeric(8,2),
  item       text,
  url        text,
  oferta     boolean,
  candidatos int,
  primary key (fecha, cadena, producto)
);

-- Seguridad: activar RLS y permitir solo INSERT desde la app
alter table public.eventos            enable row level security;
alter table public.aportes            enable row level security;
alter table public.opiniones          enable row level security;
alter table public.precios_super_hist enable row level security;   -- sin políticas: solo la clave de servicio escribe

drop policy if exists app_inserta_eventos on public.eventos;
create policy app_inserta_eventos on public.eventos for insert to anon with check (ts > now() - interval '5 minutes');
drop policy if exists app_inserta_aportes on public.aportes;
create policy app_inserta_aportes on public.aportes for insert to anon with check (ts > now() - interval '5 minutes');
drop policy if exists app_inserta_opiniones on public.opiniones;
create policy app_inserta_opiniones on public.opiniones for insert to anon with check (ts > now() - interval '5 minutes');

revoke select, update, delete on public.eventos, public.aportes, public.opiniones, public.precios_super_hist from anon;
grant insert on public.eventos, public.aportes, public.opiniones to anon;

-- 5) Registro opcional (v0.7): nombre y celular con consentimiento explícito. Solo INSERT para la app; nadie lee desde afuera.
--    Antes de abrir la app al público: inscribir este banco de datos ante la ANPD y publicar la política de privacidad (Ley 29733).
create table if not exists public.personas (
  id             bigint generated always as identity primary key,
  ts             timestamptz not null default now(),
  sesion         text not null check (char_length(sesion) between 8 and 64),
  nombre         text not null check (char_length(nombre) between 2 and 60),
  telefono       text not null check (telefono ~ '^9[0-9]{8}$'),
  consentimiento boolean not null check (consentimiento),
  version        text check (char_length(version) <= 20)
);
create index if not exists personas_sesion on public.personas (sesion);
alter table public.personas enable row level security;
drop policy if exists app_inserta_personas on public.personas;
create policy app_inserta_personas on public.personas for insert to anon with check (ts > now() - interval '5 minutes' and consentimiento);
revoke select, update, delete on public.personas from anon;
grant insert on public.personas to anon;

-- 6) Platos más elegidos (solo totales, sin datos personales): elegir un plato pesa 1; descargar la lista pesa 2 por plato.
create or replace function public.acuanto_platos_top(dias int default 60)
returns jsonb
language sql
security definer
set search_path = public
stable
as $$
  with e as (
    select evento, datos from eventos
    where ts > now() - make_interval(days => least(greatest(dias, 1), 365)) and evento in ('plato_dia', 'descargar_lista')),
  p as (
    select datos->>'plato' as plato, 1 as peso from e where evento = 'plato_dia' and datos ? 'plato'
    union all
    select jsonb_array_elements_text(datos->'platos'), 2 from e where evento = 'descargar_lista' and jsonb_typeof(datos->'platos') = 'array')
  select coalesce(jsonb_object_agg(plato, n), '{}'::jsonb) from (
    select plato, sum(peso) as n from p where plato ~ '^[a-z0-9-]{2,40}$' group by plato order by n desc limit 200) t;
$$;
revoke all on function public.acuanto_platos_top(int) from public;
grant execute on function public.acuanto_platos_top(int) to anon, authenticated;

-- Resumen agregado (sin filas sueltas ni textos) para el tablero
create or replace function public.acuanto_resumen(dias int default 30)
returns jsonb
language sql
security definer
set search_path = public
stable
as $$
  with e as (select * from eventos where ts > now() - make_interval(days => least(greatest(dias, 1), 365)))
  select jsonb_build_object(
    'desde', (now() - make_interval(days => least(greatest(dias, 1), 365)))::date,
    'personas_unicas', (select count(distinct sesion) from e),
    'eventos', (select count(*) from e),
    'por_dia', (select coalesce(jsonb_agg(x order by x->>'dia'), '[]') from (
        select jsonb_build_object('dia', ts::date, 'personas', count(distinct sesion), 'eventos', count(*)) x
        from e group by ts::date) t),
    'embudo', jsonb_build_object(
        'abrieron',        (select count(distinct sesion) from e where evento = 'abrir'),
        'eligieron_plato', (select count(distinct sesion) from e where evento = 'plato_dia'),
        'vieron_canasta',  (select count(distinct sesion) from e where evento = 'ver_canasta'),
        'vieron_lista',    (select count(distinct sesion) from e where evento = 'ver_lista'),
        'en_mercado',      (select count(distinct sesion) from e where evento = 'modo_mercado'),
        'opinaron',        (select count(distinct sesion) from opiniones where ts > now() - make_interval(days => least(greatest(dias, 1), 365)))),
    'roles', (select coalesce(jsonb_object_agg(coalesce(rol, 'sin_rol'), n), '{}') from (
        select rol, count(distinct sesion) n from e group by rol) t),
    'platos_top', (select coalesce(jsonb_agg(x), '[]') from (
        select jsonb_build_object('plato', datos->>'plato', 'veces', count(*)) x
        from e where evento = 'plato_dia' and datos ? 'plato'
        group by datos->>'plato' order by count(*) desc limit 15) t),
    'productos_vistos', (select coalesce(jsonb_agg(x), '[]') from (
        select jsonb_build_object('producto', datos->>'producto', 'veces', count(*)) x
        from e where evento = 'ver_producto' and datos ? 'producto'
        group by datos->>'producto' order by count(*) desc limit 15) t),
    'distritos', (select coalesce(jsonb_agg(x), '[]') from (
        select jsonb_build_object('distrito', datos->>'distrito', 'personas', count(distinct sesion)) x
        from e where evento = 'abrir' and datos ? 'distrito'
        group by datos->>'distrito' order by count(distinct sesion) desc limit 15) t),
    'lugar_mas_barato', (select coalesce(jsonb_agg(x), '[]') from (
        select jsonb_build_object('lugar', datos->>'lugar', 'veces', count(*)) x
        from e where evento = 'ver_canasta' and datos ? 'lugar'
        group by datos->>'lugar' order by count(*) desc limit 10) t),
    'canasta_promedio', (select round(avg((datos->>'total')::numeric), 2) from e where evento = 'ver_canasta' and datos ? 'total'),
    'resto_food_cost_promedio', (select round(avg((datos->>'food_cost')::numeric), 3) from e where evento = 'ver_costos' and datos ? 'food_cost'),
    'opiniones', (select jsonb_build_object(
        'total', count(*),
        'nota', (select coalesce(jsonb_object_agg(coalesce(nota, 'sin_nota'), n), '{}') from (select nota, count(*) n from opiniones group by nota) a),
        'pago', (select coalesce(jsonb_object_agg(pago, n), '{}') from (select pago, count(*) n from opiniones where pago is not null group by pago) b),
        'frecuencia', (select coalesce(jsonb_object_agg(frecuencia, n), '{}') from (select frecuencia, count(*) n from opiniones where frecuencia is not null group by frecuencia) c))
      from opiniones),
    'aportes', (select count(*) from aportes where ts > now() - make_interval(days => least(greatest(dias, 1), 365)))
  );
$$;
revoke all on function public.acuanto_resumen(int) from public;
grant execute on function public.acuanto_resumen(int) to anon, authenticated;
