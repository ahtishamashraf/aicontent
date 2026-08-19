# Architecture

The browser uses same-origin `/api/v1` requests. Next.js proxies these to FastAPI.
FastAPI owns validation, authentication, authorization and PostgreSQL records,
then Celery workers consume Redis jobs. Workers decrypt temporary input, run the
process-local detector provider, persist non-reversible results, and purge content
unless retention was explicitly selected. The provider boundary supports a
safetensors-preferred ModernBERT implementation and an explicit test-only fake.
