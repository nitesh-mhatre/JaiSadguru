"""Vendored Kronos foundation model for financial candlesticks.

Public surface mirrors the upstream ``model`` package so that upstream examples
and documentation remain a valid reference.

    from vendor.kronos import Kronos, KronosTokenizer, KronosPredictor

    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    predictor = KronosPredictor(model, tokenizer, max_context=512)

See :mod:`vendor.kronos.kronos` for the vendoring notes and licence.
"""

from .kronos import Kronos, KronosPredictor, KronosTokenizer

__all__ = ["Kronos", "KronosTokenizer", "KronosPredictor"]
