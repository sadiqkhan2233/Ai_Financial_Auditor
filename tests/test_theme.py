from ui.theme import chip, stepper_html


def test_chip_escapes_text():
    html = chip("<b>x</b>", "ok")
    assert "<b>" not in html and "chip ok" in html


def test_stepper_marks_the_first_unfinished_step_as_current():
    html = stepper_html([("A", True), ("B", False), ("C", False)])
    assert html.count("step done") == 1
    assert html.count("step current") == 1
    assert html.count("step todo") == 1
