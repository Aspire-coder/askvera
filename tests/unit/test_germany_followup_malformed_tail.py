from utils.directory_fields import remove_unrequested_directory_fields


QUESTION = "And what is the minimum order size there?"


def test_removing_an_unrequested_field_does_not_leave_germany_stub() -> None:
    answer = (
        "The FBO minimum order size for FBOs is EUR 100. "
        "Keep in mind that payment methods accepted are credit card and bank transfer. "
        "Is there anything else about Germany's ordering or policies I can help clarify?"
    )

    repaired, changed = remove_unrequested_directory_fields(answer, QUESTION)

    assert changed is True
    assert "payment methods accepted" not in repaired
    assert "Keep in mind that Is there" not in repaired
    assert repaired == (
        "The FBO minimum order size for FBOs is EUR 100. "
        "Is there anything else about Germany's ordering or policies I can help clarify?"
    )


def test_factual_lead_is_trimmed_not_deleted() -> None:
    answer = "Orders ship the same day and the payment methods accepted are cash. Anything else?"

    repaired, changed = remove_unrequested_directory_fields(answer, QUESTION)

    assert changed is True
    assert repaired == "Orders ship the same day. Anything else?"
