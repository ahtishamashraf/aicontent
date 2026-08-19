# THREAT MODEL
OriginLens implements a same-origin Next.js and FastAPI platform backed by PostgreSQL,
Redis and a local open-source detector. Submitted text is sensitive: it is never logged,
is encrypted during temporary persistence, and is removed after processing unless an
authenticated user explicitly retains it. Guest records expire within 24 hours.

The public AI signal score uses identity calibration and conservative 0–34, 35–64,
and 65–100 display bands. It is an estimate rather than proof or a calibrated
probability. English-only training, dataset bias, length, domain shift, editing,
translation, and adversarial transformations can produce false positives or negatives.
Use human review and additional evidence for consequential decisions.
