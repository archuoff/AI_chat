"""Picture describing: cost modes, answer parsing, sharing one description between identical pictures."""
import io
from types import SimpleNamespace

from PIL import Image

from app.images import catalog, describe
from app.ingestion.models import RawImage


def img(location, w=800, h=600):
    return SimpleNamespace(location=location, width=w, height=h)


def png(color):
    im = Image.new("RGB", (400, 300), color)
    im.paste((10, 200, 10), (50, 50, 250, 200))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_excel_pictures_use_the_cheap_mode_and_others_the_full_one():
    assert describe._mode(img({"sheet": "S", "cell": "D5"})) == "brief"
    assert describe._mode(img({"page": 3})) == "full" and describe._mode(img({"slide": 2})) == "full"
    brief, full = describe.estimate([img({"sheet": "S"})]), describe.estimate([img({"page": 1})])
    assert brief["brief"] == 1 and brief["input_tokens"] < full["input_tokens"] / 2 and brief["output_tokens"] < full["output_tokens"] / 2
    assert describe.estimate([img({"sheet": "S"})] * 100)["input_tokens"] == 100 * (85 + describe.BRIEF_PROMPT_TOKENS)  # low detail = 85 flat


def test_answer_parsing_strips_the_match_line_and_flags_doubt():
    text = "Summary: Radar bracket on a metal plate.\nVisible text: P/N 12345\nContext match: no"
    assert describe.parse_answer(text) == ("Summary: Radar bracket on a metal plate.\nVisible text: P/N 12345", False, "Context may not match the picture")
    assert describe.parse_answer("Summary: x\nContext match: yes") == ("Summary: x", False, "")
    assert describe.parse_answer("Summary: x\nContext match: unsure")[2] == "Context match unsure"
    assert describe.parse_answer("DECORATIVE.") == ("", True, "")


def test_one_call_serves_every_copy_of_the_same_picture(api):
    same, other = png((200, 30, 30)), png((30, 30, 200))
    raws = [RawImage(same, "png", {"sheet": "S", "row": r, "cell": f"D{r}"}, f"row {r}") for r in (5, 6, 7)] + \
           [RawImage(other, "png", {"sheet": "S", "row": 8, "cell": "D8"}, "row 8")]
    catalog.sync("doc1", raws)
    rows = catalog.list_images("doc1")
    assert [r.status for r in rows] == ["waiting", "skipped", "skipped", "waiting"]  # same car in 3 rows: not "logo noise" in Excel
    assert len(catalog.waiting(["doc1"])) == 2  # two paid calls, not four
    first = rows[0]
    catalog.record_result(first.id, description="Summary: a red car.", usage={"input_tokens": 300, "output_tokens": 40})
    assert catalog.share_with_duplicates(first.id) == 2
    done = {r.location["row"]: r for r in catalog.list_images("doc1")}
    assert [done[r].status for r in (5, 6, 7)] == ["described"] * 3 and done[7].description == "Summary: a red car."
    chunks = catalog.image_chunks("doc1", "x.xlsx", 0)
    assert sorted(c.location["row"] for c in chunks) == [5, 6, 7]  # each copy is findable next to its own row


def test_repeated_logo_in_a_pdf_is_still_skipped_but_only_from_four_places(api):
    logo = png((1, 2, 3))
    three = catalog.sync("p3", [RawImage(logo, "png", {"page": i}, "") for i in (1, 2, 3)])
    assert three["skipped"] == 2  # 3 places: only exact duplicates of the first
    four = catalog.sync("p4", [RawImage(logo, "png", {"page": i}, "") for i in (1, 2, 3, 4)])
    assert four["skipped"] == 4


class FakeVision:
    """Like AzureChatOpenAI: the length limit is a field, and bind(max_tokens=...) must never be used (Azure 400)."""

    def __init__(self, max_tokens=700):
        self.max_tokens, self.sent = max_tokens, []

    def model_copy(self, update):
        clone = FakeVision(update.get("max_tokens", self.max_tokens))
        clone.sent = self.sent
        return clone

    def bind(self, **kw):
        raise AssertionError("bind(max_tokens=...) sends both max_tokens and max_completion_tokens")

    def invoke(self, messages):
        self.sent.append((self.max_tokens, messages))
        return SimpleNamespace(content="Summary: red car\nContext match: yes", usage_metadata={"input_tokens": 100, "output_tokens": 10})


def test_brief_mode_limits_the_answer_with_a_copy_not_with_bind(api):
    catalog.sync("d1", [RawImage(png((200, 30, 30)), "png", {"sheet": "S", "row": 5, "cell": "D5"}, "Sheet: S"),
                        RawImage(png((30, 30, 200)), "png", {"page": 2}, "page text")])
    excel, pdf = catalog.list_images("d1")
    fake = FakeVision()
    text, usage = describe._describe_one(fake, excel, "x.xlsx")
    assert text.startswith("Summary") and usage["output_tokens"] == 10
    limit, messages = fake.sent[0]
    assert limit == 120 and messages[0][1][1]["image_url"]["detail"] == "low"  # short answer, low detail
    describe._describe_one(fake, pdf, "x.pdf")
    limit, messages = fake.sent[1]
    assert limit == 700 and messages[0][1][1]["image_url"]["detail"] == "high"  # other formats keep the full settings
