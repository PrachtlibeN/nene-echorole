from app.core.config import LLMProfile, Settings
from app.llm.fake import FakeLLMClient
from app.llm.interfaces import LLMMessage
from app.roleplay.agent import RoleplayAgent
from app.roleplay.interfaces import RoleplayContext
from app.roleplay.prompts import build_roleplay_prompt
from app.schemas.contracts import ScenarioOut, ScenarioPanelPersona


def make_scenario() -> ScenarioOut:
    return ScenarioOut.model_validate(
        {
            "id": "scn_test",
            "slug": "test-interview",
            "title": "Test Interview",
            "description": "A test scenario.",
            "language": "en",
            "difficulty": 2,
            "max_turns": 8,
            "estimated_minutes": 10,
            "definition": {
                "persona": {
                    "name": "Morgan Lee",
                    "role": "Engineering Manager",
                    "style": "Direct and curious",
                    "pressure_level": 2,
                },
                "task": {
                    "goal": "Describe a project you led.",
                    "success_criteria": ["Use a concrete example", "Explain the result"],
                },
                "evaluation_focus": ["relevance", "structure"],
            },
        }
    )


def make_panel_scenario() -> ScenarioOut:
    scenario = make_scenario()
    personas = [
        ScenarioPanelPersona(
            id="alex",
            name="Alex",
            role_title="Engineering Manager",
            focus_area="Technical execution",
            voice_gender="male",
            persona_prompt="Probe technical decisions.",
        ),
        ScenarioPanelPersona(
            id="sarah",
            name="Sarah",
            role_title="People Partner",
            focus_area="Leadership and conflict",
            voice_gender="female",
            persona_prompt="Probe leadership and conflict.",
        ),
    ]
    return scenario.model_copy(
        update={
            "definition": scenario.definition.model_copy(update={"personas": personas})
        }
    )


def make_context(
    history: list[LLMMessage] | None = None,
    *,
    scenario: ScenarioOut | None = None,
    turn_index: int = 1,
) -> RoleplayContext:
    return RoleplayContext(
        session_id="ses_test",
        conversation_id="cnv_rp_test",
        scenario=scenario or make_scenario(),
        history=history or [],
        turn_index=turn_index,
        max_turns=8,
    )


def test_prompt_uses_scenario_and_sets_spoken_roleplay_boundaries() -> None:
    prompt = build_roleplay_prompt(make_scenario())

    assert "Morgan Lee" in prompt
    assert "Describe a project you led." in prompt
    assert "60 words or fewer" in prompt
    assert "Do not use Markdown, stage directions" in prompt
    assert "coaching, hints, feedback, or scores" in prompt
    assert "[END]" in prompt


def test_open_session_uses_roleplay_profile_and_returns_llm_metadata() -> None:
    settings = Settings(OLLAMA_MODEL="test-model")
    llm = FakeLLMClient(settings, replies=["Tell me about a project you led."])
    agent = RoleplayAgent(llm, settings)

    reply = agent.open_session(make_context())

    assert reply.text == "Tell me about a project you led."
    assert not reply.should_end
    assert reply.llm.model == settings.model_for(LLMProfile.ROLEPLAY)
    profile, messages, json_mode = llm.calls[0]
    assert profile is LLMProfile.ROLEPLAY
    assert len(messages) == 1
    assert messages[0].role == "system"
    assert not json_mode


def test_respond_trims_history_and_strips_end_marker_and_caps_reply() -> None:
    settings = Settings(OLLAMA_MODEL="test-model", roleplay_history_turns=2)
    reply_text = " ".join(["spoken"] * 61) + " [END]"
    llm = FakeLLMClient(settings, replies=[reply_text])
    agent = RoleplayAgent(llm, settings)
    history = [
        LLMMessage(role="assistant", content="old interviewer"),
        LLMMessage(role="user", content="old candidate"),
        LLMMessage(role="assistant", content="recent interviewer one"),
        LLMMessage(role="user", content="recent candidate one"),
        LLMMessage(role="assistant", content="recent interviewer two"),
        LLMMessage(role="user", content="recent candidate two"),
    ]

    reply = agent.respond(make_context(history), "Current answer")

    _, sent_messages, _ = llm.calls[0]
    assert [message.content for message in sent_messages[1:]] == [
        "recent interviewer one",
        "recent candidate one",
        "recent interviewer two",
        "recent candidate two",
        "Current answer",
    ]
    assert reply.should_end
    assert "[END]" not in reply.text
    assert len(reply.text.split()) == 60


def test_panel_opening_uses_both_personas_and_labels_first_speaker_in_history() -> None:
    settings = Settings(OLLAMA_MODEL="test-model")
    llm = FakeLLMClient(
        settings,
        replies=[
            "Welcome. We will discuss your project decisions.",
            "Thanks, Alex. What project did you lead under pressure?",
        ],
    )
    agent = RoleplayAgent(llm, settings)

    replies = agent.open_session(make_context(scenario=make_panel_scenario()))

    assert isinstance(replies, list)
    assert [(reply.speaker_id, reply.speaker_name) for reply in replies] == [
        ("alex", "Alex"),
        ("sarah", "Sarah"),
    ]
    assert "Do not ask the candidate a question" in llm.calls[0][1][0].content
    assert "ask the candidate one focused first question" in llm.calls[1][1][0].content
    assert llm.calls[1][1][1].content.startswith(
        "[Alex - Engineering Manager]: Welcome."
    )


def test_panel_odd_candidate_turn_gets_two_turns_with_labeled_context() -> None:
    settings = Settings(OLLAMA_MODEL="test-model")
    llm = FakeLLMClient(
        settings,
        replies=[
            "The result is useful, but explain your own role.",
            "How did you resolve the disagreement with the platform team?",
        ],
    )
    agent = RoleplayAgent(llm, settings)
    candidate_text = "I led a six-person migration."

    replies = agent.respond(
        make_context(scenario=make_panel_scenario(), turn_index=1),
        candidate_text,
    )

    assert isinstance(replies, list)
    assert [reply.speaker_id for reply in replies] == ["alex", "sarah"]
    second_history = llm.calls[1][1]
    assert second_history[-2].content == candidate_text
    assert second_history[-1].content.startswith(
        "[Alex - Engineering Manager]: The result"
    )


def test_panel_even_candidate_turns_alternate_single_speaker() -> None:
    settings = Settings(OLLAMA_MODEL="test-model")
    llm = FakeLLMClient(
        settings,
        replies=["What was the measurable outcome?", "Who did you align first?"],
    )
    agent = RoleplayAgent(llm, settings)

    second_turn = agent.respond(
        make_context(scenario=make_panel_scenario(), turn_index=2),
        "I ran the first rollout.",
    )
    fourth_turn = agent.respond(
        make_context(scenario=make_panel_scenario(), turn_index=4),
        "We reduced latency by a third.",
    )

    assert not isinstance(second_turn, list)
    assert not isinstance(fourth_turn, list)
    assert second_turn.speaker_id == "alex"
    assert fourth_turn.speaker_id == "sarah"
