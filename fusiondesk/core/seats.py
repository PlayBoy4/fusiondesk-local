"""Dynamic seat assignment for FusionDesk AI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .registry import ConnectorCatalog, ModelCatalog, SkillRegistry


VALID_MODES = {"SOLO", "RELAY", "PANEL", "TRINITY"}
VALID_SEATS = {
    "planner",
    "researcher",
    "builder",
    "reviewer",
    "risk_checker",
    "clarity_writer",
    "judge",
    "memory",
    "evidence_checker",
    "media_analyzer",
    "copywriter",
    "ads_auditor",
    "data_analyst",
    "creative_director",
    "seo_optimizer",
    "brand_guard",
    "knowledge_architect",
}
COST_QUALITY_MODES = {"cheapest", "balanced", "premium", "fastest", "highest_quality"}
MODE_SEAT_LIMITS = {
    "SOLO": 1,
    "RELAY": 2,
    "PANEL": 6,
    "TRINITY": 3,
}
COST_RANK = {
    "cheap": 1,
    "balanced": 2,
    "premium": 3,
}
SEAT_TRAITS = {
    "planner": ["reasoning_strength", "reliability"],
    "researcher": ["research_strength", "reasoning_strength", "context_length"],
    "builder": ["coding_strength", "reasoning_strength", "reliability"],
    "reviewer": ["coding_strength", "reasoning_strength", "reliability"],
    "risk_checker": ["reasoning_strength", "reliability"],
    "clarity_writer": ["writing_strength", "reliability"],
    "judge": ["reasoning_strength", "reliability"],
    "memory": ["context_length", "reliability"],
    "evidence_checker": ["research_strength", "reliability", "context_length"],
    "media_analyzer": ["research_strength", "context_length", "reasoning_strength", "reliability"],
    "copywriter": ["writing_strength", "speed", "reliability"],
    "ads_auditor": ["reasoning_strength", "research_strength", "reliability"],
    "data_analyst": ["reasoning_strength", "research_strength", "context_length"],
    "creative_director": ["writing_strength", "reasoning_strength", "reliability"],
    "seo_optimizer": ["research_strength", "writing_strength", "reliability"],
    "brand_guard": ["writing_strength", "reliability", "context_length"],
    "knowledge_architect": ["context_length", "reasoning_strength", "writing_strength", "reliability"],
}
TRAIT_ALIASES = {
    "reasoning": ["reasoning_strength"],
    "marketing": ["writing_strength", "research_strength"],
    "analysis": ["reasoning_strength", "research_strength"],
    "writing": ["writing_strength"],
}
CONNECTOR_KEYWORDS = {
    "polygon_io": {
        "market",
        "ticker",
        "stock",
        "option",
        "options",
        "premium",
        "premarket",
        "spy",
        "qqq",
        "nvda",
        "candle",
        "candles",
    },
    "agent_reach": {
        "research",
        "web",
        "source",
        "internet",
        "reddit",
        "twitter",
        "x/twitter",
        "youtube",
        "rss",
        "linkedin",
        "podcast",
        "competitor",
    },
    "github": {"repo", "github", "pull request", "issue", "code review", "bug", "test", "tests"},
    "local_filesystem": {"repo", "file", "files", "code", "bug", "test", "tests", "local"},
    "runpod": {"runpod", "gpu", "video", "wan2gp", "comfyui", "flux", "image generation", "media generation", "clip generation", "autoshorts"},
    "openrouter": {"model", "llm", "agent", "seat", "prompt"},
}


@dataclass(frozen=True)
class SeatAssignmentEngine:
    skills: SkillRegistry
    connectors: ConnectorCatalog
    models: ModelCatalog

    @classmethod
    def load(cls) -> "SeatAssignmentEngine":
        return cls(
            skills=SkillRegistry.load(),
            connectors=ConnectorCatalog.load(),
            models=ModelCatalog.load(),
        )

    def assign(
        self,
        task: str,
        selected_skill: str | dict[str, Any] | None = None,
        mode: str | None = None,
        available_models: list[str] | None = None,
        connector_requirements: list[str] | None = None,
        cost_preference: str = "balanced",
        quality_preference: str = "balanced",
    ) -> dict[str, Any]:
        skill, skill_confidence, skill_warning = self._resolve_skill(task, selected_skill)
        selected_mode = self._resolve_mode(mode, skill)
        cost_mode = _normalize_preference(cost_preference)
        quality_mode = _normalize_preference(quality_preference)
        connectors = self._resolve_connectors(task, skill, connector_requirements)
        seats = self._resolve_seats(skill, selected_mode)
        model_pool, unknown_model_count = self._resolve_models(available_models)
        assignments = [
            self._assign_model_to_seat(
                seat=seat,
                skill=skill,
                connectors=connectors,
                model_pool=model_pool,
                cost_mode=cost_mode,
                quality_mode=quality_mode,
            )
            for seat in seats
        ]
        warnings = []
        if skill_warning:
            warnings.append(skill_warning)
        if unknown_model_count:
            warnings.append(f"{unknown_model_count} model(s) used fallback capability profiles")

        confidence = self._confidence(
            skill_confidence=skill_confidence,
            assignments=assignments,
            connectors=connectors,
            warnings=warnings,
        )

        return {
            "task": task,
            "selected_skill": skill["id"],
            "mode": selected_mode,
            "connectors": connectors,
            "seat_assignments": assignments,
            "estimated_cost_tier": self._estimated_cost_tier(assignments, cost_mode),
            "confidence": confidence,
            "warnings": warnings,
        }

    def _resolve_skill(
        self, task: str, selected_skill: str | dict[str, Any] | None
    ) -> tuple[dict[str, Any], float, str | None]:
        if isinstance(selected_skill, dict):
            return selected_skill, 0.95, None
        if isinstance(selected_skill, str):
            try:
                return self.skills.get(selected_skill), 0.95, None
            except KeyError:
                fallback = self._best_skill_match(task)
                if fallback:
                    return fallback, 0.55, f"Unsupported skill '{selected_skill}', selected closest trigger match"
                return self.skills.get("orchestration.solo"), 0.35, f"Unsupported skill '{selected_skill}', using orchestration.solo"

        fallback = self._best_skill_match(task)
        if fallback:
            return fallback, 0.8, None
        return self.skills.get("orchestration.solo"), 0.45, "No skill trigger matched, using orchestration.solo"

    def _best_skill_match(self, task: str) -> dict[str, Any] | None:
        matches = self.skills.match_triggers(task)
        if matches:
            return sorted(matches, key=lambda skill: len(skill.get("trigger_phrases", [])), reverse=True)[0]
        return None

    def _resolve_mode(self, mode: str | None, skill: dict[str, Any]) -> str:
        if mode in VALID_MODES:
            return mode
        skill_mode = skill.get("default_mode", "SOLO")
        if skill_mode in VALID_MODES:
            return skill_mode
        return "SOLO"

    def _resolve_connectors(
        self,
        task: str,
        skill: dict[str, Any],
        connector_requirements: list[str] | None,
    ) -> list[str]:
        known = {connector["id"] for connector in self.connectors.connectors}
        selected = set(skill.get("required_tools", []))
        selected.update(connector_requirements or [])

        task_lc = task.casefold()
        for connector_id, keywords in CONNECTOR_KEYWORDS.items():
            if any(keyword in task_lc for keyword in keywords):
                selected.add(connector_id)

        selected.add("openrouter")
        return sorted(connector for connector in selected if connector in known)

    def _resolve_seats(self, skill: dict[str, Any], mode: str) -> list[str]:
        required = _dedupe(skill.get("required_seats", []))
        optional = _dedupe(skill.get("optional_seats", []))
        seats = [seat for seat in required + optional if seat in VALID_SEATS]
        limit = MODE_SEAT_LIMITS[mode]
        if not seats:
            seats = ["builder"]
        return seats[:limit]

    def _resolve_models(self, available_models: list[str] | None) -> tuple[list[dict[str, Any]], int]:
        profiles = {profile["id"]: profile for profile in self.models.profiles}
        if available_models is None:
            return list(profiles.values()), 0

        selected = []
        unknown = 0
        for model_id in available_models:
            if model_id in profiles:
                selected.append(profiles[model_id])
            else:
                selected.append(_fallback_model_profile(model_id))
                unknown += 1
        if not selected:
            selected.append(_fallback_model_profile("fusiondesk-fallback-model"))
            unknown += 1
        return selected, unknown

    def _assign_model_to_seat(
        self,
        seat: str,
        skill: dict[str, Any],
        connectors: list[str],
        model_pool: list[dict[str, Any]],
        cost_mode: str,
        quality_mode: str,
    ) -> dict[str, str]:
        scored = [
            (
                _score_model(
                    model=model,
                    seat=seat,
                    skill=skill,
                    connectors=connectors,
                    cost_mode=cost_mode,
                    quality_mode=quality_mode,
                ),
                model,
            )
            for model in model_pool
        ]
        score, model = max(scored, key=lambda item: item[0])
        return {
            "seat": seat,
            "model": model["id"],
            "reason": _reason_for_assignment(model, seat, skill, cost_mode, quality_mode, score),
        }

    def _estimated_cost_tier(self, assignments: list[dict[str, str]], cost_mode: str) -> str:
        if cost_mode in {"cheapest", "fastest"}:
            return cost_mode
        tiers = []
        profile_by_id = {profile["id"]: profile for profile in self.models.profiles}
        for assignment in assignments:
            profile = profile_by_id.get(assignment["model"])
            if profile:
                tiers.append(COST_RANK.get(profile.get("cost_tier", "balanced"), 2))
        if not tiers:
            return "balanced"
        average = sum(tiers) / len(tiers)
        if average <= 1.4:
            return "cheapest"
        if average >= 2.6:
            return "premium"
        return "balanced"

    def _confidence(
        self,
        skill_confidence: float,
        assignments: list[dict[str, str]],
        connectors: list[str],
        warnings: list[str],
    ) -> float:
        confidence = skill_confidence
        if assignments:
            confidence += 0.06
        if connectors:
            confidence += 0.04
        confidence -= len(warnings) * 0.15
        return round(max(0.1, min(confidence, 0.97)), 2)


def _score_model(
    model: dict[str, Any],
    seat: str,
    skill: dict[str, Any],
    connectors: list[str],
    cost_mode: str,
    quality_mode: str,
) -> float:
    seat_traits = SEAT_TRAITS.get(seat, ["reasoning_strength", "reliability"])
    skill_traits = skill.get("preferred_model_traits", [])
    traits = _expand_traits(_dedupe(seat_traits + skill_traits))
    score = sum(float(model.get(trait, 5)) for trait in traits) / max(len(traits), 1)

    if "agent_reach" in connectors and seat in {"researcher", "evidence_checker"}:
        score += float(model.get("research_strength", 5)) * 0.2
        score += float(model.get("context_length", 5)) * 0.1
    if "github" in connectors or "local_filesystem" in connectors:
        if seat in {"builder", "reviewer"}:
            score += float(model.get("coding_strength", 5)) * 0.25
    if "polygon_io" in connectors and seat in {"risk_checker", "judge", "researcher"}:
        score += float(model.get("reasoning_strength", 5)) * 0.2
        score += float(model.get("reliability", 5)) * 0.15
    if "runpod" in connectors and seat in {"planner", "builder", "risk_checker"}:
        score += float(model.get("reasoning_strength", 5)) * 0.15

    cost_rank = COST_RANK.get(model.get("cost_tier", "balanced"), 2)
    if cost_mode == "cheapest":
        score += (4 - cost_rank) * 2.5
    elif cost_mode == "balanced":
        score += 1.2 if cost_rank == 2 else 0.4
    elif cost_mode == "premium":
        score += cost_rank * 1.8
    elif cost_mode == "fastest":
        score += float(model.get("speed", 5)) * 1.6
        score += (4 - cost_rank) * 0.7
    elif cost_mode == "highest_quality":
        score += float(model.get("reasoning_strength", 5)) * 0.7
        score += float(model.get("reliability", 5)) * 0.5

    if quality_mode == "highest_quality":
        score += float(model.get("reasoning_strength", 5)) * 0.4
        score += float(model.get("reliability", 5)) * 0.4
    elif quality_mode == "premium":
        score += cost_rank
    elif quality_mode == "fastest":
        score += float(model.get("speed", 5)) * 0.8
    elif quality_mode == "cheapest":
        score += (4 - cost_rank) * 1.1

    return score


def _reason_for_assignment(
    model: dict[str, Any],
    seat: str,
    skill: dict[str, Any],
    cost_mode: str,
    quality_mode: str,
    score: float,
) -> str:
    traits = _expand_traits(_dedupe(SEAT_TRAITS.get(seat, []) + skill.get("preferred_model_traits", [])))
    best_traits = sorted(traits, key=lambda trait: model.get(trait, 0), reverse=True)[:2]
    trait_text = ", ".join(trait.replace("_", " ") for trait in best_traits) or "general capability"
    mode_text = cost_mode if cost_mode == quality_mode else f"{cost_mode}/{quality_mode}"
    return f"Best {seat} fit for {trait_text} under {mode_text} preference; score {score:.2f}"


def _fallback_model_profile(model_id: str) -> dict[str, Any]:
    return {
        "id": model_id,
        "display_name": model_id,
        "coding_strength": 5,
        "reasoning_strength": 5,
        "research_strength": 5,
        "writing_strength": 5,
        "speed": 5,
        "cost_tier": "balanced",
        "context_length": 5,
        "reliability": 4,
        "preferred_use_cases": ["fallback"],
    }


def _normalize_preference(value: str | None) -> str:
    if value in COST_QUALITY_MODES:
        return value
    return "balanced"


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _expand_traits(values: list[str]) -> list[str]:
    expanded = []
    for value in values:
        expanded.extend(TRAIT_ALIASES.get(value, [value]))
    return _dedupe(expanded)
