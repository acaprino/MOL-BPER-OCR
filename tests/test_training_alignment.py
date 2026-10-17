"""Behavioral checks for converting reviewed values into OCR token labels."""
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from training.alignment import align_screen


def _line(image: Image.Image, text: str, x: int, y: int) -> dict[str, Any]:
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    box = draw.textbbox((x, y), text, font=font)
    draw.text((x, y), text, fill="black", font=font)
    left, top, right, bottom = box
    return {"text": text, "score": 1.0,
            "box": [[left - 1, top - 1], [right + 1, top - 1],
                    [right + 1, bottom + 1], [left - 1, bottom + 1]]}


def test_field_alignment_does_not_take_a_token_from_the_existing_loans_table() -> None:
    image = Image.new("RGB", (900, 300), "white")
    lines = [_line(image, text, x, y) for text, x, y in [
        ("FIDI", 10, 10), ("Fido", 10, 40), ("Rapporto", 90, 40),
        ("Importo", 200, 40), ("Fido", 400, 40),
        ("F1", 10, 70), ("123456", 90, 70), ("789012", 410, 70),
    ]]
    result = align_screen("GestioneFidi", [("n° FIDO", "F1"),
                                           ("Rapporto", "123456 789012")], lines, image)
    field = result["fields"]["Rapporto"]
    assert field["status"] == "unresolved"
    assert field["indices"] == []


def test_repetitive_long_notes_retain_the_last_reviewed_words() -> None:
    image = Image.new("RGB", (1000, 400), "white")
    texts = ["La richiesta di finanziamento rispetta i criteri concordati con il cliente."] * 5
    texts.append("La verifica finale comprende anche la scadenza conclusiva.")
    lines = [_line(image, text, 150, 30 + i * 24) for i, text in enumerate(texts)]
    lines.append(_line(image, "testo estraneo non revisionato", 150, 210))
    result = align_screen("Note", [("Note della richiesta", " ".join(texts))], lines, image)
    field = result["fields"]["Note della richiesta"]
    assert field["status"] == "aligned"
    selected = [result["words"][i]["text"] for i in field["indices"]]
    assert selected[-1] == "conclusiva."
    assert "estraneo" not in selected


def test_long_note_verifies_matching_words_around_an_ocr_error() -> None:
    image = Image.new("RGB", (1000, 400), "white")
    expected = ["La richiesta di finanziamento rispetta i criteri concordati con il cliente."] * 5
    expected.append("La scadenza prevista comprende 361 mesi dopo la verifica conclusiva.")
    observed = [*expected[:-1], expected[-1].replace("361", "381")]
    lines = [_line(image, text, 150, 30 + i * 24) for i, text in enumerate(observed)]
    result = align_screen("Note", [("Note della richiesta", " ".join(expected))], lines, image)
    field = result["fields"]["Note della richiesta"]
    verified = [result["words"][i]["text"] for i in field["verified_indices"]]
    assert field["exact_text"] is False
    assert verified[:2] == ["La", "richiesta"]
    assert verified[-2:] == ["verifica", "conclusiva."]
    assert "381" not in verified
    assert len(verified) == sum(len(text.split()) for text in expected) - 1


def test_matching_a_six_preserves_the_original_ocr_eight() -> None:
    image = Image.new("RGB", (900, 200), "white")
    lines = [_line(image, text, x, y) for text, x, y in [
        ("NDG", 30, 30), ("Denom.", 180, 30), ("38214802", 30, 65),
    ]]
    result = align_screen("Elenco", [("NDG", "36214802")], lines, image)
    field = result["fields"]["NDG"]
    assert field["status"] == "aligned"
    assert field["ocr_text"] == "38214802"
    assert field["exact_text"] is False
    assert result["words"][field["indices"][0]]["text"] == "38214802"


def test_validation_timestamp_verifies_date_but_excludes_the_misread_word() -> None:
    image = Image.new("RGB", (1100, 220), "white")
    lines = [_line(image, text, x, y) for text, x, y in [
        ("Ultima validazione", 600, 30),
        ("30/09/2026 (4 glorni fa)", 600, 75),
    ]]
    field_name = "Ultima validazione scheda privati"
    result = align_screen("Scheda_Privati_1", [(field_name, "30/09/2026 (4 giorni fa)")],
                          lines, image)
    field = result["fields"][field_name]
    verified = [result["words"][i]["text"] for i in field["verified_indices"]]
    assert field["exact_text"] is False
    assert "30/09/2026" in verified
    assert "glorni" not in verified
    assert len(verified) == 3


def test_field_alignment_keeps_source_punctuation_between_matched_words() -> None:
    image = Image.new("RGB", (1100, 220), "white")
    lines = [_line(image, "Filiale relazione: 145 - PR S LAZZARO", 300, 50)]
    result = align_screen("GestioneFidi", [("Filiale relazione", "145 - PR S LAZZARO")],
                          lines, image)
    field = result["fields"]["Filiale relazione"]
    selected = [result["words"][i]["text"] for i in field["indices"]]
    assert selected == ["145", "-", "PR", "S", "LAZZARO"]
    assert field["exact_text"] is True


def test_missing_punctuation_does_not_count_as_whole_field_exact() -> None:
    image = Image.new("RGB", (900, 200), "white")
    lines = [_line(image, text, x, y) for text, x, y in [
        ("NDG", 30, 30), ("Denom.", 180, 30),
        ("21310900", 30, 65), ("LUCIAC", 180, 65),
    ]]
    result = align_screen("Elenco", [("DENOMINAZIONE", "LUCIAC ...")], lines, image)
    field = result["fields"]["DENOMINAZIONE"]
    assert field["ocr_text"] == "LUCIAC"
    assert field["exact_text"] is False


def test_partial_note_verification_keeps_punctuation_meaningful() -> None:
    image = Image.new("RGB", (1000, 220), "white")
    lines = [_line(image, "Cliente La scadenza prevista richiede verifica conclusiva.", 150, 50)]
    expected = "Cliente. La scadenza prevista richiede verifica conclusiva."
    result = align_screen("Note", [("Note della richiesta", expected)], lines, image)
    field = result["fields"]["Note della richiesta"]
    verified = [result["words"][i]["text"] for i in field["verified_indices"]]
    assert "Cliente" not in verified
    assert "scadenza" in verified
    assert "conclusiva." in verified
    assert field["exact_text"] is False


def test_absent_subject_has_no_box_or_positive_token_indices() -> None:
    image = Image.new("RGB", (900, 200), "white")
    lines = [_line(image, text, x, y) for text, x, y in [
        ("NDG", 30, 30), ("Denominazione", 180, 30), ("Ruolo", 400, 30),
        ("21310900", 30, 65), ("ZHENG LINA", 180, 65), ("Richiedente", 400, 65),
    ]]
    result = align_screen("Soggetti", [("NDG 4", "")], lines, image)
    assert result["fields"]["NDG 4"] == {
        "indices": [], "bbox": None, "status": "empty", "ocr_text": "", "exact_text": True,
    }


def test_word_bounds_follow_asymmetric_ink_instead_of_character_count() -> None:
    image = Image.new("RGB", (400, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 53, 41, 59), fill="black")
    draw.rectangle((100, 53, 155, 59), fill="black")
    lines = [{"text": "III WWW", "score": 1.0,
              "box": [[25, 50], [160, 50], [160, 63], [25, 63]]}]
    result = align_screen("unknown", [], lines, image)
    first, second = result["words"]
    assert (first["x0"], first["x1"]) == (30, 42)
    assert (second["x0"], second["x1"]) == (100, 156)


def test_two_line_table_cell_orders_top_line_before_centered_bottom_line() -> None:
    image = Image.new("RGB", (900, 220), "white")
    lines = [
        _line(image, "FIDI", 10, 10),
        _line(image, "Fido Rapporto Descrizione Importo", 10, 40),
        {"text": "Proposta", "score": 1.0, "box": [[10, 74], [60, 74], [60, 87], [10, 87]]},
        {"text": "F1", "score": 1.0, "box": [[80, 74], [95, 74], [95, 87], [80, 87]]},
        {"text": "034 0744 0017", "score": 1.0, "box": [[120, 70], [210, 70], [210, 83], [120, 83]]},
        {"text": "M.FOND.PRIVATI", "score": 1.0, "box": [[230, 74], [310, 74], [310, 87], [230, 87]]},
        {"text": "135.800", "score": 1.0, "box": [[330, 74], [380, 74], [380, 87], [330, 87]]},
        {"text": "05502254", "score": 1.0, "box": [[130, 78], [185, 78], [185, 91], [130, 91]]},
    ]
    result = align_screen(
        "GestioneFidi",
        [("n° FIDO", "F1"), ("Rapporto", "034 0744 0017 05502254")],
        lines,
        image,
    )
    field = result["fields"]["Rapporto"]
    assert field["status"] == "aligned"
    assert field["ocr_text"] == "034 0744 0017 05502254"
    assert field["exact_text"] is True


def test_unresolved_fidi_cell_scopes_uncertainty_box_to_its_row() -> None:
    from training.dataset import apply_supervision

    image = Image.new("RGB", (900, 260), "white")
    lines = [
        _line(image, "Menu Laterale Statico", 10, 10),
        _line(image, "FIDI", 100, 40),
        _line(image, "Fido Rapporto Scadenza Importo", 100, 70),
        _line(image, "Fido", 500, 70),
        _line(image, "F1", 100, 105),
        _line(image, "36o es5", 220, 105),
        _line(image, "140.000", 300, 105),
        _line(image, "GARANZIE", 100, 170),
        _line(image, "Altro testo di sfondo", 100, 200),
    ]
    result = align_screen(
        "GestioneFidi",
        [("n° FIDO", "F1"), ("Scadenza", "360 mesi"), ("Importo (€)", "140.000")],
        lines,
        image,
    )
    scadenza = result["fields"]["Scadenza"]
    assert scadenza["status"] == "unresolved"
    assert scadenza["bbox"] is not None
    labels, _ = apply_supervision(
        result["words"],
        result["fields"],
        {"n° FIDO": "n_fido", "Scadenza": "scadenza", "Importo (€)": "importo_euro"},
    )
    by_text = {w["text"]: label for w, label in zip(result["words"], labels)}
    assert by_text["F1"] == "n_fido"
    assert by_text["140.000"] == "importo_euro"
    assert by_text["36o"] == "IGNORE"
    assert by_text["es5"] == "IGNORE"
    assert by_text["Statico"] == "O"
    assert by_text["sfondo"] == "O"


def test_scadenza_with_six_eight_ocr_error_verifies_exact_unit_word() -> None:
    from training.dataset import apply_supervision

    image = Image.new("RGB", (900, 200), "white")
    lines = [
        _line(image, "FIDI", 100, 20),
        _line(image, "Fido Scadenza Importo Fido", 100, 50),
        _line(image, "F1", 100, 85),
        _line(image, "381 mesi", 180, 85),
    ]
    result = align_screen(
        "GestioneFidi",
        [("n° FIDO", "F1"), ("Scadenza", "361 mesi")],
        lines,
        image,
    )
    scadenza = result["fields"]["Scadenza"]
    assert scadenza["status"] == "aligned"
    assert scadenza["exact_text"] is False
    verified = [result["words"][i]["text"] for i in scadenza.get("verified_indices", [])]
    assert verified == ["mesi"]
    labels, states = apply_supervision(
        result["words"],
        result["fields"],
        {"n° FIDO": "n_fido", "Scadenza": "scadenza"},
    )
    by_text = {w["text"]: label for w, label in zip(result["words"], labels)}
    assert by_text["381"] == "IGNORE"
    assert by_text["mesi"] == "scadenza"
    assert states["Scadenza"] == "partial_supervision"


