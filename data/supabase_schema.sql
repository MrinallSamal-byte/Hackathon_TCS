-- CampusBite Supabase schema (Postgres). Idempotent: safe to run twice.
-- Run in Supabase SQL editor, or: psql "$SUPABASE_DB_URL" -f data/supabase_schema.sql
-- Follows supabase-postgres-best-practices: PKs, CHECKs, TIMESTAMPTZ defaults,
-- partial index for the hot live-menu path, GIN for tag arrays, RLS on.

-- ============ menu_items ============
create table if not exists public.menu_items (
  id                 text primary key,
  name               text not null,
  description        text not null default '',
  price              numeric not null check (price >= 0),
  category           text not null,
  cuisine            text not null,
  ingredients        text[] not null default '{}',
  allergens          text[] not null default '{}',
  dietary_tags       text[] not null default '{}',
  availability       boolean not null default true,
  available_until    text,
  prep_time_minutes  integer not null check (prep_time_minutes between 2 and 25),
  calories           integer not null default 0 check (calories >= 0),
  portion_size       text not null,
  spice_level        integer not null default 0 check (spice_level between 0 and 3),
  taste_profile      text[] not null default '{}',
  mood_tags          text[] not null default '{}',
  serving_times      text[] not null default '{all_day}',
  popularity_score   integer not null default 50 check (popularity_score between 0 and 100),
  is_combo           boolean not null default false,
  combo_items        text[] not null default '{}',
  updated_at         timestamptz not null default now()
);

-- Hot path: live menu filtered by price/prep. Partial index keeps it small.
create index if not exists menu_items_live_price_prep_idx
  on public.menu_items (price, prep_time_minutes)
  where availability = true;
create index if not exists menu_items_category_idx
  on public.menu_items (category);
create index if not exists menu_items_dietary_gin
  on public.menu_items using gin (dietary_tags);

-- ============ feedback_log ============
create table if not exists public.feedback_log (
  id         bigint generated always as identity primary key,
  item_id    text not null references public.menu_items (id) on delete cascade,
  rating     smallint not null check (rating in (-1, 1)),
  comment    text,
  budget     numeric,
  mood       text,
  created_at timestamptz not null default now()
);
create index if not exists feedback_log_item_idx on public.feedback_log (item_id);

-- ============ order_history ============
create table if not exists public.order_history (
  id         bigint generated always as identity primary key,
  token      text not null,
  tray       text[] not null default '{}',
  total      numeric not null default 0,
  budget     numeric,
  eta        integer,
  created_at timestamptz not null default now()
);
create index if not exists order_history_token_idx on public.order_history (token);

-- ============ RLS (service key bypasses; anon gets read + feedback/order writes) ============
alter table public.menu_items   enable row level security;
alter table public.feedback_log enable row level security;
alter table public.order_history enable row level security;

drop policy if exists "public read menu" on public.menu_items;
create policy "public read menu" on public.menu_items
  for select using (true);

drop policy if exists "public insert feedback" on public.feedback_log;
create policy "public insert feedback" on public.feedback_log
  for insert with check (true);

drop policy if exists "public insert orders" on public.order_history;
create policy "public insert orders" on public.order_history
  for insert with check (true);

-- ============ chat_memory (per-session AI memory) ============
create table if not exists public.chat_memory (
  session_id text primary key,
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

-- ============ migration: columns for features added after the first seed ====
-- Idempotent: safe to run on a database created from any earlier version.
-- Nutrition estimates (estimates, not lab values) power diabetic/low-carb goals.
alter table public.menu_items
  add column if not exists protein_g integer not null default 0 check (protein_g >= 0);
alter table public.menu_items
  add column if not exists carbs_g integer not null default 0 check (carbs_g >= 0);
alter table public.menu_items
  add column if not exists sugar_g integer not null default 0 check (sugar_g >= 0);
alter table public.menu_items
  add column if not exists fiber_g integer not null default 0 check (fiber_g >= 0);

-- Coupons / pickup counters / status overrides + session link for My Orders.
alter table public.order_history
  add column if not exists session_id text;
alter table public.order_history
  add column if not exists payable numeric not null default 0;
alter table public.order_history
  add column if not exists coupon text;
alter table public.order_history
  add column if not exists discount numeric not null default 0;
alter table public.order_history
  add column if not exists counter text;
alter table public.order_history
  add column if not exists counter_label text;
alter table public.order_history
  add column if not exists status_override text
    check (status_override in ('READY', 'COMPLETED', 'CANCELLED'));

-- Session link for per-user feedback trends.
alter table public.feedback_log
  add column if not exists session_id text;

create index if not exists order_history_session_idx on public.order_history (session_id);
create index if not exists feedback_log_session_idx on public.feedback_log (session_id);

alter table public.chat_memory enable row level security;

drop policy if exists "public upsert own memory" on public.chat_memory;
create policy "public upsert own memory" on public.chat_memory
  for all using (true) with check (true);
-- NOTE: demo-friendly open policy. For production, scope session_id to the
-- authenticated user (auth.uid()) instead of `true`.
