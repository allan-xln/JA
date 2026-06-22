-- Optional prerequisite for PostgreSQL installations without gen_random_uuid().
-- Do not include this file in the normal migration sequence.
-- Run it separately only with a role allowed to manage extensions.

create extension if not exists pgcrypto;
