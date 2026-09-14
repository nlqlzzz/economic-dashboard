-- Decision Log MVP. Run this file in Supabase SQL Editor.
create extension if not exists pgcrypto;

create table if not exists public.investment_decisions (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    decision_at timestamptz not null,
    ticker text not null,
    security_code text not null,
    company_name text not null,
    decision_action text not null,
    horizon_trading_days integer not null,
    reason_tags text[] not null default '{}',
    comment text,
    review_condition text,
    decision_mode text not null,
    decision_source text not null,
    reference_price numeric not null,
    reference_price_date date not null,
    benchmark_ticker text not null default '1306.T',
    benchmark_price numeric not null,
    benchmark_price_date date not null,
    data_snapshot jsonb not null,
    schema_version integer not null default 1,
    supersedes_decision_id uuid null references public.investment_decisions(id),
    constraint investment_decisions_action_check
        check (decision_action in ('買う', '見送る', '保有継続', '売却')),
    constraint investment_decisions_horizon_check
        check (horizon_trading_days in (20, 60, 120)),
    constraint investment_decisions_mode_check
        check (decision_mode in ('実判断', '仮想判断')),
    constraint investment_decisions_source_check
        check (decision_source = 'Human'),
    constraint investment_decisions_reason_count_check
        check (cardinality(reason_tags) <= 3),
    constraint investment_decisions_reason_values_check
        check (reason_tags <@ array[
            '業績', '会社予想', '評価水準', '株価・モメンタム', 'TOPIX比',
            '市場感応度', 'マクロ環境', 'テーマ・業界', 'リスク', 'その他'
        ]::text[]),
    constraint investment_decisions_comment_length_check
        check (comment is null or char_length(comment) <= 300),
    constraint investment_decisions_review_length_check
        check (review_condition is null or char_length(review_condition) <= 300),
    constraint investment_decisions_reference_price_check
        check (reference_price > 0 and benchmark_price > 0),
    constraint investment_decisions_reference_dates_check
        check (reference_price_date = benchmark_price_date),
    constraint investment_decisions_snapshot_object_check
        check (jsonb_typeof(data_snapshot) = 'object'),
    constraint investment_decisions_schema_version_check
        check (schema_version > 0)
);

create index if not exists investment_decisions_decision_at_idx
    on public.investment_decisions (decision_at desc);
create index if not exists investment_decisions_ticker_decision_at_idx
    on public.investment_decisions (ticker, decision_at desc);

alter table public.investment_decisions enable row level security;
alter table public.investment_decisions force row level security;

-- No anon/authenticated policy is created. Browser-side keys cannot read or write this table.
revoke all on table public.investment_decisions from anon, authenticated;
revoke all on table public.investment_decisions from service_role;
grant select, insert on table public.investment_decisions to service_role;

comment on table public.investment_decisions is
    'Append-only human investment decisions with point-in-time analysis snapshots.';
