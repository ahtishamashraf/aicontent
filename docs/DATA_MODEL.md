# Data model
UUID-keyed users own sessions and analyses. Analyses own ordered segments and
feedback. Email tokens are hashed and single-use. Usage events, model versions,
admin audit records, and typed system settings support operations. PostgreSQL
foreign keys define cascades; sensitive text is versioned-envelope encrypted.
