# Legacy clustering archive

These files document the deprecated clustering experiment and are not imported
by the production room-assignment application.

Clustering labels are not a defensible substitute for room assignment:

- clusters do not enforce room capacity;
- cluster validation indices do not measure roommate outcomes;
- the old workflow mixed encoded and human-readable datasets; and
- serialized models are environment-specific research artifacts.

Do not restore these modules to `app.py` or the `engine` package. They remain
only for historical reproducibility.
