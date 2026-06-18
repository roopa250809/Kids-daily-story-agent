from src.story_agent import (
    check_story_repetition,
    send_approved_story_now,
    story_uses_child_interest,
    story_uses_favorite_character_type,
)
from src.story_email import format_story_email_html, get_email_mode, send_story_email
from src.story_image import build_illustration_prompt
from src.story_memory import format_mem0_memories, remember_child_fact, search_child_memory
from src.story_pdf import create_story_pdf
from src.story_storage import DEFAULT_PROFILE
from src.story_audio import generate_story_audio


def test_email_sender_blocks_without_parent_approval(monkeypatch):
    monkeypatch.setattr("src.story_email.log_email_status", lambda entry: entry)

    result = send_story_email(
        to_email="parent@example.com",
        subject="Story",
        body="Once upon a time.",
        story_id="story-test",
        approved=False,
    )

    assert result["status"] == "blocked"


def test_gmail_smtp_mode_detection(monkeypatch):
    monkeypatch.setenv("STORY_AGENT_MOCK_EMAIL", "false")
    monkeypatch.setenv("GMAIL_ADDRESS", "parent@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")

    assert get_email_mode() == "gmail_smtp"


def test_placeholder_email_config_is_not_real_smtp(monkeypatch):
    monkeypatch.setenv("STORY_AGENT_MOCK_EMAIL", "false")
    monkeypatch.setenv("GMAIL_ADDRESS", "your_email@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "your_16_character_app_password")
    monkeypatch.setenv("SMTP_USERNAME", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")

    assert get_email_mode() == "missing_smtp_config"


def test_real_email_reports_missing_config(monkeypatch):
    monkeypatch.setattr("src.story_email.log_email_status", lambda entry: entry)
    monkeypatch.setenv("STORY_AGENT_MOCK_EMAIL", "false")
    monkeypatch.setenv("GMAIL_ADDRESS", "your_email@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "your_16_character_app_password")
    monkeypatch.setenv("SMTP_USERNAME", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")

    result = send_story_email(
        to_email="parent@example.com",
        subject="Story",
        body="Once upon a time.",
        story_id="story-test",
        approved=True,
    )

    assert result["status"] == "failed_config"


def test_mock_email_records_pdf_attachment(monkeypatch, tmp_path):
    monkeypatch.setattr("src.story_email.log_email_status", lambda entry: entry)
    monkeypatch.setenv("STORY_AGENT_MOCK_EMAIL", "true")
    pdf_path = tmp_path / "story.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    result = send_story_email(
        to_email="parent@example.com",
        subject="Story",
        body="Once upon a time.",
        story_id="story-test",
        approved=True,
        attachment_paths=[str(pdf_path)],
    )

    assert result["status"] == "mock_sent"
    assert str(pdf_path) in result["attachments"]
    assert result["attachment_count"] == "1"


def test_real_email_message_includes_pdf_attachment(monkeypatch, tmp_path):
    monkeypatch.setattr("src.story_email.log_email_status", lambda entry: entry)
    monkeypatch.setenv("STORY_AGENT_MOCK_EMAIL", "false")
    monkeypatch.setenv("GMAIL_ADDRESS", "parent@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    pdf_path = tmp_path / "story.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    result = send_story_email(
        to_email="parent@example.com",
        subject="Story",
        body="Once upon a time.",
        story_id="story-test",
        approved=True,
        attachment_paths=[str(pdf_path)],
    )

    assert result["status"] == "sent"
    assert result["attachment_names"] == "story.pdf"
    assert sent_messages
    attachments = [
        part for part in sent_messages[0].walk()
        if part.get_content_disposition() == "attachment"
    ]
    assert attachments[0].get_filename() == "story.pdf"
    assert attachments[0].get_content_type() == "application/pdf"


def test_real_email_message_includes_mp3_attachment(monkeypatch, tmp_path):
    monkeypatch.setattr("src.story_email.log_email_status", lambda entry: entry)
    monkeypatch.setenv("STORY_AGENT_MOCK_EMAIL", "false")
    monkeypatch.setenv("GMAIL_ADDRESS", "parent@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    audio_path = tmp_path / "story.mp3"
    audio_path.write_bytes(b"fake-mp3")
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    result = send_story_email(
        to_email="parent@example.com",
        subject="Story",
        body="Once upon a time.",
        story_id="story-test",
        approved=True,
        attachment_paths=[str(audio_path)],
    )

    attachments = [
        part for part in sent_messages[0].walk()
        if part.get_content_disposition() == "attachment"
    ]
    assert result["status"] == "sent"
    assert attachments[0].get_filename() == "story.mp3"
    assert attachments[0].get_content_type() == "audio/mpeg"


def test_generate_story_audio_skips_without_key(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")

    result = generate_story_audio(
        title="Story",
        story_text="Once upon a time.",
        parent_note="Be kind.",
        story_id="story-test",
    )

    assert result["status"] == "skipped"


def test_generate_story_audio_writes_mp3(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr("src.story_audio.AUDIO_DIR", tmp_path)
    calls = []

    class FakeResponse:
        content = b"audio-bytes"

        def raise_for_status(self):
            pass

    def fake_post(url, headers, params, json, timeout):
        calls.append({"url": url, "headers": headers, "params": params, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("httpx.post", fake_post)

    result = generate_story_audio(
        title="Story",
        story_text="Once upon a time.",
        parent_note="Be kind.",
        story_id="story-test",
    )

    assert result["status"] == "generated"
    assert result["audio_path"].endswith(".mp3")
    assert open(result["audio_path"], "rb").read() == b"audio-bytes"
    assert calls[0]["headers"]["xi-api-key"] == "test-key"
    assert calls[0]["json"]["text"].startswith("Story.")


def test_direct_send_blocks_when_required_image_missing(monkeypatch):
    monkeypatch.setattr(
        "src.story_agent.generate_illustration_node",
        lambda state: {
            "illustration_status": "failed",
            "illustration_error": "image provider unavailable",
            "illustration_path": "",
            "illustration_url": "",
        },
    )

    result = send_approved_story_now(
        {
            "child_id": "demo-child",
            "child_profile": {"child_name": "Maya", "parent_email": "parent@example.com"},
            "story_id": "story-test",
            "story_title": "Test Story",
            "selected_theme": "kindness",
            "story_text": "Once upon a time.",
            "parent_note": "Be kind.",
        }
    )

    assert result["status"] == "email_failed"
    assert result["email_result"]["status"] == "blocked_missing_image"


def test_send_email_blocks_when_audio_requested_but_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.story_agent.create_story_pdf",
        lambda **kwargs: str(tmp_path / "story.pdf"),
    )
    (tmp_path / "story.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        "src.story_agent.generate_story_audio",
        lambda **kwargs: {"status": "skipped", "reason": "missing key", "audio_path": ""},
    )
    monkeypatch.setattr(
        "src.story_agent.send_story_email",
        lambda **kwargs: {"status": "sent"},
    )

    result = send_approved_story_now(
        {
            "child_id": "demo-child",
            "child_profile": {"child_name": "Maya", "parent_email": "parent@example.com"},
            "story_id": "story-test",
            "story_title": "Test Story",
            "selected_theme": "kindness",
            "story_text": "Once upon a time.",
            "parent_note": "Be kind.",
            "illustration_path": "existing-image.png",
        },
        include_audio=True,
    )

    assert result["status"] == "email_failed"
    assert result["email_result"]["status"] == "blocked_missing_audio"


def test_create_story_pdf_writes_pdf_file():
    path = create_story_pdf(
        child_name="Maya",
        title="Maya and the Snow Princess",
        theme="kindness",
        story_text="Maya met a snow princess.\nThey shared a kind light.",
        parent_note="Kindness can be small and bright.",
        story_id="story-test-pdf",
    )

    assert path.endswith(".pdf")
    assert open(path, "rb").read(4) == b"%PDF"


def test_create_story_pdf_can_include_illustration(tmp_path):
    from PIL import Image
    from pypdf import PdfReader

    image_path = tmp_path / "story.png"
    Image.new("RGB", (120, 120), color=(216, 108, 89)).save(image_path)

    path = create_story_pdf(
        child_name="Maya",
        title="Maya and the Snow Princess",
        theme="kindness",
        story_text="Maya met a snow princess.",
        parent_note="Kindness can be small and bright.",
        story_id="story-test-pdf-image",
        illustration_path=str(image_path),
    )
    reader = PdfReader(path)
    resources = reader.pages[0].get("/Resources", {})
    xobjects = resources.get("/XObject", {})

    assert path.endswith(".pdf")
    assert xobjects


def test_format_mem0_memories_normalizes_sdk_results():
    result = format_mem0_memories(
        [
            {"memory": "Baby A likes snow princess helpers."},
            {"text": "Parent prefers short stories."},
            "Avoid angry characters.",
        ]
    )

    assert result == [
        "Baby A likes snow princess helpers.",
        "Parent prefers short stories.",
        "Avoid angry characters.",
    ]


def test_default_profile_includes_gender():
    assert DEFAULT_PROFILE["gender"] == "prefer not to say"


def test_mem0_search_uses_child_id_as_user_id(monkeypatch):
    calls = []

    class FakeClient:
        def search(self, query, user_id, limit):
            calls.append({"query": query, "user_id": user_id, "limit": limit})
            return [{"memory": "Baby A likes gentle pig stories."}]

    monkeypatch.setattr("src.story_memory.get_mem0_client", lambda: FakeClient())

    result = search_child_memory("demo-child", "story preferences", limit=3)

    assert result == [{"memory": "Baby A likes gentle pig stories."}]
    assert calls == [{"query": "story preferences", "user_id": "demo-child", "limit": 3}]


def test_mem0_add_uses_child_id_as_user_id(monkeypatch):
    calls = []

    class FakeClient:
        def add(self, messages, user_id):
            calls.append({"messages": messages, "user_id": user_id})

    monkeypatch.setattr("src.story_memory.get_mem0_client", lambda: FakeClient())

    assert remember_child_fact("demo-child", "Baby A likes short bedtime stories.") is True
    assert calls == [
        {
            "messages": [{"role": "user", "content": "Baby A likes short bedtime stories."}],
            "user_id": "demo-child",
        }
    ]


def test_repetition_checker_flags_similar_recent_story():
    result = check_story_repetition(
        theme="kindness",
        characters=["robot", "moon"],
        setting="space",
        summary="A robot helps the moon and learns kindness.",
        recent_stories=[
            {
                "story_id": "story-old",
                "story_title": "The Kind Robot",
                "theme": "kindness",
                "characters": ["robot", "moon"],
                "setting": "space",
                "story_summary": "A robot helps the moon and learns to be kind.",
            }
        ],
    )

    assert result["is_repetitive"] is True
    assert result["similar_story_id"] == "story-old"


def test_illustration_prompt_is_child_safe():
    prompt = build_illustration_prompt(
        {
            "child_profile": {
                "age": 6,
                "gender": "girl",
                "interests": ["space", "soccer"],
                "topics_to_avoid": ["scary stories"],
            },
            "story_title": "Maya and the Moon Ball",
            "selected_theme": "kindness",
            "setting": "a quiet backyard",
            "characters": ["Maya", "moon"],
        }
    )

    assert "storybook illustration" in prompt
    assert "Child gender: girl" in prompt
    assert "depict the child as a girl around age 6" in prompt
    assert "no scary imagery" in prompt
    assert "no copyrighted characters" in prompt


def test_illustration_prompt_uses_gender_neutral_when_unspecified():
    prompt = build_illustration_prompt(
        {
            "child_profile": {
                "age": 4,
                "gender": "prefer not to say",
                "interests": ["blocks"],
                "topics_to_avoid": [],
            },
            "story_title": "The Gentle Tower",
            "selected_theme": "patience",
            "setting": "a playroom",
            "characters": ["child", "tower"],
        }
    )

    assert "Child gender: prefer not to say" in prompt
    assert "keep the child visually gender-neutral" in prompt


def test_html_email_includes_illustration_url():
    html = format_story_email_html(
        child_name="Maya",
        title="Maya and the Moon Ball",
        theme="kindness",
        story_text="Once upon a time.",
        illustration_url="https://example.com/image.png",
    )

    assert "https://example.com/image.png" in html
    assert "<img" in html
    assert "width:220px" in html


def test_html_email_can_reference_inline_illustration():
    html = format_story_email_html(
        child_name="Maya",
        title="Maya and the Moon Ball",
        theme="kindness",
        story_text="Once upon a time.",
        illustration_cid="story-illustration",
    )

    assert "cid:story-illustration" in html
    assert "<img" in html
    assert "width:220px" in html


def test_story_interest_checker_requires_saved_interest():
    result = story_uses_child_interest(
        {
            "child_profile": {"interests": ["space", "soccer"]},
            "story_title": "Maya Learns Kindness",
            "story_summary": "Maya helps a friend in the garden.",
            "story_text": "Maya shares a blanket and listens carefully.",
            "characters": ["Maya"],
            "setting": "a garden",
        }
    )

    assert result["uses_interest"] is False


def test_story_interest_checker_accepts_interest_detail():
    result = story_uses_child_interest(
        {
            "child_profile": {"interests": ["space", "soccer"]},
            "story_title": "Maya and the Moon Ball",
            "story_summary": "Maya shares a soccer ball under the stars.",
            "story_text": "Maya kicks her soccer ball gently to a friend while looking up at space.",
            "characters": ["Maya"],
            "setting": "a backyard",
        }
    )

    assert result["uses_interest"] is True
    assert "soccer" in result["matched_interests"]


def test_story_interest_checker_requires_every_saved_interest():
    result = story_uses_child_interest(
        {
            "child_profile": {"interests": ["dog", "forest"]},
            "story_title": "Maya and the Forest Path",
            "story_summary": "Maya explores the forest kindly.",
            "story_text": "Maya walks through the forest and helps a friend.",
            "characters": ["Maya"],
            "setting": "a forest",
        }
    )

    assert result["uses_interest"] is False
    assert result["missing_interests"] == ["dog"]


def test_story_favorite_character_checker_requires_one_character_type():
    result = story_uses_favorite_character_type(
        {
            "child_profile": {"favorite_characters": ["friendly robot", "curious explorer"]},
            "story_title": "Maya Learns Kindness",
            "story_summary": "Maya helps a friend in the garden.",
            "story_text": "Maya shares a blanket and listens carefully.",
            "characters": ["Maya"],
            "setting": "a garden",
        }
    )

    assert result["uses_favorite_character"] is False


def test_story_favorite_character_checker_accepts_matching_type():
    result = story_uses_favorite_character_type(
        {
            "child_profile": {"favorite_characters": ["friendly robot", "curious explorer"]},
            "story_title": "Maya and the Kind Robot",
            "story_summary": "A friendly robot helps Maya practice kindness.",
            "story_text": "The robot carried a tiny lantern through the garden.",
            "characters": ["Maya", "friendly robot"],
            "setting": "a garden",
        }
    )

    assert result["uses_favorite_character"] is True
    assert "friendly robot" in result["matched_favorite_characters"]


def test_story_favorite_character_checker_accepts_safe_inspiration_for_elsa():
    result = story_uses_favorite_character_type(
        {
            "child_profile": {"favorite_characters": ["Elsa"]},
            "story_title": "Baby A and the Snow Princess",
            "story_summary": "A snow princess helps Baby A practice kindness.",
            "story_text": "The snow princess shared a gentle snowflake light.",
            "characters": ["Baby A", "snow princess"],
            "setting": "a snowy garden",
        }
    )

    assert result["uses_favorite_character"] is True
    assert "snow princess" in result["matched_favorite_characters"]
