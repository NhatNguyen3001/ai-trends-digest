"""Collectors — one module per external source.

Each collector talks to a single source (arXiv, GitHub, news, RSS) and returns
a list of the pipeline's common ``Item`` type. They all share that one return
shape so the rest of the pipeline never has to care where an item came from.
"""
