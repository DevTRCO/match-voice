from matchvoice.pipeline import proof


def test_proof_catches_every_injected_error_and_passes_the_real_lines():
    out = proof.build()  # raises if an injected error is not caught for the expected reason
    assert all(c["ok"] for c in out["checked"]) and len(out["checked"]) == 6
    assert {a["code"] for a in out["attacks"]} == {"score_mismatch", "number_unsupported", "player_unsupported", "language_mismatch"}
