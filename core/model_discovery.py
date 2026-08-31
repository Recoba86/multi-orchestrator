"""Read-only model declaration discovery, separate from config and resolution.

Provides local declaration discovery (Codex profiles and agent TOMLs),
native OpenAI/Codex account model discovery (from authenticated models cache),
and provider-agnostic Codex Router supply discovery (merged catalog, enabled providers,
and user model picker visibility) with fail-closed corruption detection and a unified pool.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping
import tomllib


@dataclass(frozen=True)
class DiscoveryResult:
    source: str
    available: bool
    models: tuple[str, ...] = ()
    detail: str = ""
    family_map: Mapping[str, str] | None = None


@dataclass(frozen=True)
class NativeCodexModel:
    slug: str
    display_name: str
    description: str
    model_family: str
    context_window: int
    max_context_window: int | None
    default_reasoning_effort: str | None
    reasoning_levels: tuple[str, ...]
    input_modalities: tuple[str, ...]
    supports_vision: bool
    supports_tools: bool
    supports_search: bool
    visibility: str
    eligible: bool
    source: str = "native-codex"


@dataclass(frozen=True)
class NativeCodexSupplySnapshot:
    available: bool
    error: str | None
    models: tuple[NativeCodexModel, ...]
    eligible_models: tuple[NativeCodexModel, ...]
    distinct_families: tuple[str, ...]
    slug_to_family: Mapping[str, str]


@dataclass(frozen=True)
class NormalizedSupplyModel:
    router_slug: str
    provider: str
    upstream_model_id: str
    display_name: str
    route_type: str
    model_family: str
    context_window: int
    auto_compact: int | None
    max_output: int | None
    default_reasoning_effort: str | None
    reasoning_levels: tuple[str, ...]
    input_modalities: tuple[str, ...]
    supports_vision: bool
    supports_tools: bool
    supports_search: bool
    request_profile: str | None
    visible: bool
    provider_enabled: bool
    eligible: bool
    metadata_source: str
    source: str = "codex-router"


@dataclass(frozen=True)
class CodexRouterSupplySnapshot:
    state_dir: Path
    available: bool
    error: str | None
    enabled_providers: tuple[str, ...]
    discovered_models: tuple[NormalizedSupplyModel, ...]
    eligible_models: tuple[NormalizedSupplyModel, ...]
    hidden_models: tuple[NormalizedSupplyModel, ...]
    stale_visible_slugs: tuple[str, ...]
    distinct_families: tuple[str, ...]
    family_to_models: Mapping[str, tuple[NormalizedSupplyModel, ...]]
    slug_to_family: Mapping[str, str]


@dataclass(frozen=True)
class UnifiedModelEntry:
    slug: str
    display_name: str
    source: str  # "native-codex" | "codex-router"
    provider: str
    route_type: str  # "NATIVE" | "DIRECT" | "COMBO" | "UNKNOWN"
    model_family: str
    context_window: int
    default_reasoning_effort: str | None
    reasoning_levels: tuple[str, ...]
    supports_vision: bool
    supports_tools: bool
    supports_search: bool


@dataclass(frozen=True)
class UnifiedModelSupplySnapshot:
    available: bool
    native_supply: NativeCodexSupplySnapshot
    router_supply: CodexRouterSupplySnapshot
    all_eligible_models: tuple[UnifiedModelEntry, ...]
    distinct_families: tuple[str, ...]
    slug_to_family: Mapping[str, str]
    family_to_models: Mapping[str, tuple[UnifiedModelEntry, ...]]


def derive_model_family(slug: str, metadata: Mapping[str, Any] | None = None) -> str:
    """Derive logical model family representing cognitive lineage."""
    meta = metadata or {}
    if "model_family" in meta and isinstance(meta["model_family"], str) and meta["model_family"].strip():
        return meta["model_family"].strip().upper()

    slug_lower = slug.lower()
    if "opus" in slug_lower:
        return "OPUS"
    if "deepseek" in slug_lower:
        return "DEEPSEEK_V4"
    if "gemini" in slug_lower:
        return "GEMINI_3_7_FLASH"
    if "grok" in slug_lower:
        return "GROK_4_6"
    if "glm" in slug_lower:
        return "GLM_5_3"
    if "qwen" in slug_lower:
        return "QWEN_3_8"
    if "composer" in slug_lower:
        return "COMPOSER_2_5"
    if "step" in slug_lower:
        return "STEP_3_7"
    if "kimi" in slug_lower:
        return "KIMI_K3"
    if "sol" in slug_lower:
        return "GPT_5_6_SOL"
    if "luna" in slug_lower:
        return "GPT_5_6_LUNA"
    if "terra" in slug_lower:
        return "GPT_5_6_TERRA"
    if slug_lower in ("gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "codex-auto-review") or slug_lower.startswith("gpt-5."):
        return "GPT_5_SERIES"

    return "UNKNOWN"


def load_native_codex_supply(target_home: str | Path | None = None) -> NativeCodexSupplySnapshot:
    """Load native OpenAI/Codex models available to authenticated account from models_cache.json."""
    home = Path(target_home).expanduser() if target_home else Path.home()
    cache_file = home / ".codex" / "models_cache.json"

    if not cache_file.is_file():
        return NativeCodexSupplySnapshot(
            available=False,
            error="models_cache.json not found",
            models=(),
            eligible_models=(),
            distinct_families=(),
            slug_to_family={},
        )

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("models_cache.json root is not a dict")
        raw_models = data.get("models", [])
        if not isinstance(raw_models, list):
            raise ValueError("models_cache.json 'models' key is not a list")
    except Exception as e:
        return NativeCodexSupplySnapshot(
            available=False,
            error=f"models_cache.json is corrupt or unreadable: {e}",
            models=(),
            eligible_models=(),
            distinct_families=(),
            slug_to_family={},
        )

    discovered: list[NativeCodexModel] = []
    eligible: list[NativeCodexModel] = []
    slug_to_fam: dict[str, str] = {}

    for m in raw_models:
        if not isinstance(m, dict):
            continue
        slug = m.get("slug")
        if not slug or not isinstance(slug, str):
            continue

        display_name = m.get("display_name") or slug
        desc = m.get("description") or ""
        family = derive_model_family(slug)
        slug_to_fam[slug] = family

        ctx = m.get("context_window", 272000)
        max_ctx = m.get("max_context_window")
        def_effort = m.get("default_reasoning_level")
        r_levels: tuple[str, ...] = tuple(
            x.get("effort")
            for x in m.get("supported_reasoning_levels", [])
            if isinstance(x, dict) and "effort" in x
        )
        modalities = tuple(m.get("input_modalities", ["text"]))
        supports_vis = "image" in modalities
        supports_tls = m.get("supports_parallel_tool_calls", True) or m.get("supports_tools", True)
        supports_srch = m.get("supports_search_tool", False) or m.get("supports_search", False)
        vis = m.get("visibility", "list")
        # Native models with visibility "hide" (e.g. codex-auto-review) are internal
        is_eligible = (vis != "hide")

        model_entry = NativeCodexModel(
            slug=slug,
            display_name=display_name,
            description=desc,
            model_family=family,
            context_window=ctx,
            max_context_window=max_ctx,
            default_reasoning_effort=def_effort,
            reasoning_levels=r_levels,
            input_modalities=modalities,
            supports_vision=supports_vis,
            supports_tools=supports_tls,
            supports_search=supports_srch,
            visibility=vis,
            eligible=is_eligible,
        )
        discovered.append(model_entry)
        if is_eligible:
            eligible.append(model_entry)

    distinct_fams = tuple(sorted(set(m.model_family for m in eligible)))

    return NativeCodexSupplySnapshot(
        available=True,
        error=None,
        models=tuple(discovered),
        eligible_models=tuple(eligible),
        distinct_families=distinct_fams,
        slug_to_family=slug_to_fam,
    )


def load_codex_router_supply(target_home: str | Path | None = None) -> CodexRouterSupplySnapshot:
    """Load and normalize current Codex Router model supply without executing network requests."""
    home = Path(target_home).expanduser() if target_home else Path.home()
    state_dir = home / ".codex" / "codex-router"

    if not state_dir.is_dir():
        return CodexRouterSupplySnapshot(
            state_dir=state_dir,
            available=False,
            error="router state directory not found",
            enabled_providers=(),
            discovered_models=(),
            eligible_models=(),
            hidden_models=(),
            stale_visible_slugs=(),
            distinct_families=(),
            family_to_models={},
            slug_to_family={},
        )

    # 1. Enabled Native Providers
    enabled_providers_file = state_dir / "enabled-providers.json"
    enabled_native: set[str] = set()
    if enabled_providers_file.is_file():
        try:
            p_data = json.loads(enabled_providers_file.read_text(encoding="utf-8"))
            if not isinstance(p_data, dict):
                raise ValueError("enabled-providers.json root is not a dict")
            enabled_native = set(p_data.get("providers", []))
        except Exception as e:
            return CodexRouterSupplySnapshot(
                state_dir=state_dir,
                available=False,
                error=f"enabled-providers.json is corrupt or unreadable: {e}",
                enabled_providers=(),
                discovered_models=(),
                eligible_models=(),
                hidden_models=(),
                stale_visible_slugs=(),
                distinct_families=(),
                family_to_models={},
                slug_to_family={},
            )

    # 2. Enabled Generic Providers
    generic_providers_file = state_dir / "generic-providers.json"
    enabled_generic: set[str] = set()
    if generic_providers_file.is_file():
        try:
            g_data = json.loads(generic_providers_file.read_text(encoding="utf-8"))
            if not isinstance(g_data, dict):
                raise ValueError("generic-providers.json root is not a dict")
            for p in g_data.get("providers", []):
                if isinstance(p, dict) and p.get("enabled", True):
                    enabled_generic.add(p["id"])
        except Exception as e:
            return CodexRouterSupplySnapshot(
                state_dir=state_dir,
                available=False,
                error=f"generic-providers.json is corrupt or unreadable: {e}",
                enabled_providers=(),
                discovered_models=(),
                eligible_models=(),
                hidden_models=(),
                stale_visible_slugs=(),
                distinct_families=(),
                family_to_models={},
                slug_to_family={},
            )

    all_enabled_providers = enabled_native | enabled_generic

    # 3. Model Picker State
    picker_file = state_dir / "model-picker.json"
    visible_slugs: set[str] = set()
    hidden_slugs: set[str] = set()
    if picker_file.is_file():
        try:
            pk_data = json.loads(picker_file.read_text(encoding="utf-8"))
            if not isinstance(pk_data, dict):
                raise ValueError("model-picker.json root is not a dict")
            visible_slugs = set(pk_data.get("visible", []))
            hidden_slugs = set(pk_data.get("hidden", []))
        except Exception as e:
            return CodexRouterSupplySnapshot(
                state_dir=state_dir,
                available=False,
                error=f"model-picker.json is corrupt or unreadable: {e}",
                enabled_providers=(),
                discovered_models=(),
                eligible_models=(),
                hidden_models=(),
                stale_visible_slugs=(),
                distinct_families=(),
                family_to_models={},
                slug_to_family={},
            )

    # 4. User Curated Models (Custom metadata & NineRouter)
    user_models_file = state_dir / "user-models.json"
    user_models_map: dict[str, dict[str, Any]] = {}
    if user_models_file.is_file():
        try:
            u_data = json.loads(user_models_file.read_text(encoding="utf-8"))
            if not isinstance(u_data, dict):
                raise ValueError("user-models.json root is not a dict")
            for m in u_data.get("models", []):
                if isinstance(m, dict) and "slug" in m:
                    user_models_map[m["slug"]] = m
        except Exception as e:
            return CodexRouterSupplySnapshot(
                state_dir=state_dir,
                available=False,
                error=f"user-models.json is corrupt or unreadable: {e}",
                enabled_providers=(),
                discovered_models=(),
                eligible_models=(),
                hidden_models=(),
                stale_visible_slugs=(),
                distinct_families=(),
                family_to_models={},
                slug_to_family={},
            )

    # 5. Merged Models Catalog
    merged_models_file = state_dir / "merged-models.json"
    merged_models_list: list[dict[str, Any]] = []
    if merged_models_file.is_file():
        try:
            m_data = json.loads(merged_models_file.read_text(encoding="utf-8"))
            if not isinstance(m_data, dict):
                raise ValueError("merged-models.json root is not a dict")
            merged_models_list = m_data.get("models", [])
        except Exception as e:
            return CodexRouterSupplySnapshot(
                state_dir=state_dir,
                available=False,
                error=f"merged-models.json is corrupt or unreadable: {e}",
                enabled_providers=(),
                discovered_models=(),
                eligible_models=(),
                hidden_models=(),
                stale_visible_slugs=(),
                distinct_families=(),
                family_to_models={},
                slug_to_family={},
            )

    discovered: list[NormalizedSupplyModel] = []
    eligible: list[NormalizedSupplyModel] = []
    hidden: list[NormalizedSupplyModel] = []
    catalog_slugs: set[str] = set()
    slug_to_fam: dict[str, str] = {}

    for m in merged_models_list:
        if not isinstance(m, dict):
            continue
        slug = m.get("slug")
        if not slug or not isinstance(slug, str):
            continue
        catalog_slugs.add(slug)

        prov = slug.split("/")[0] if "/" in slug else "openai"
        is_prov_enabled = prov in all_enabled_providers
        is_vis = slug in visible_slugs and slug not in hidden_slugs

        u_meta = user_models_map.get(slug, {})

        up_id = u_meta.get("upstreamModel") or m.get("upstream_model") or m.get("model") or slug
        route_type = u_meta.get("route_type") or ("DIRECT" if "/" in slug else "UNKNOWN")
        family = derive_model_family(slug, u_meta)
        slug_to_fam[slug] = family

        ctx = m.get("context_window") or u_meta.get("contextWindow") or 131072
        auto_compact = m.get("auto_compact_token_limit") or u_meta.get("autoCompact")
        max_output = m.get("max_output_tokens") or u_meta.get("maxOutput")

        def_effort = m.get("default_reasoning_level") or u_meta.get("defaultEffort")
        r_levels: tuple[str, ...] = ()
        if "supported_reasoning_levels" in m and isinstance(m["supported_reasoning_levels"], list):
            r_levels = tuple(l.get("effort") for l in m["supported_reasoning_levels"] if isinstance(l, dict) and "effort" in l)
        elif "reasoningLevels" in u_meta and isinstance(u_meta["reasoningLevels"], list):
            r_levels = tuple(l.get("effort") for l in u_meta["reasoningLevels"] if isinstance(l, dict) and "effort" in l)

        modalities = tuple(m.get("input_modalities", ["text"]))
        supports_vis = "image" in modalities or m.get("supports_vision", False)
        supports_tls = m.get("supports_tools", True)
        supports_srch = m.get("supports_search", False)
        req_profile = u_meta.get("requestProfile")

        meta_source = "user-models.json" if slug in user_models_map else "merged-models.json"
        is_eligible = is_prov_enabled and is_vis

        norm_model = NormalizedSupplyModel(
            router_slug=slug,
            provider=prov,
            upstream_model_id=up_id,
            display_name=m.get("display_name") or u_meta.get("displayName") or slug,
            route_type=route_type,
            model_family=family,
            context_window=ctx,
            auto_compact=auto_compact,
            max_output=max_output,
            default_reasoning_effort=def_effort,
            reasoning_levels=r_levels,
            input_modalities=modalities,
            supports_vision=supports_vis,
            supports_tools=supports_tls,
            supports_search=supports_srch,
            request_profile=req_profile,
            visible=is_vis,
            provider_enabled=is_prov_enabled,
            eligible=is_eligible,
            metadata_source=meta_source,
        )

        if is_prov_enabled:
            discovered.append(norm_model)

        if is_eligible:
            eligible.append(norm_model)
        elif is_prov_enabled and not is_vis:
            hidden.append(norm_model)

    stale_visible = tuple(sorted(s for s in visible_slugs if s not in catalog_slugs or s.split("/")[0] not in all_enabled_providers))

    fam_map: dict[str, list[NormalizedSupplyModel]] = {}
    for em in eligible:
        fam_map.setdefault(em.model_family, []).append(em)

    distinct_fams = tuple(sorted(fam_map.keys()))
    frozen_fam_map = {k: tuple(v) for k, v in fam_map.items()}

    return CodexRouterSupplySnapshot(
        state_dir=state_dir,
        available=True,
        error=None,
        enabled_providers=tuple(sorted(all_enabled_providers)),
        discovered_models=tuple(discovered),
        eligible_models=tuple(eligible),
        hidden_models=tuple(hidden),
        stale_visible_slugs=stale_visible,
        distinct_families=distinct_fams,
        family_to_models=frozen_fam_map,
        slug_to_family=slug_to_fam,
    )


def load_unified_model_supply(target_home: str | Path | None = None) -> UnifiedModelSupplySnapshot:
    """Load both native Codex models and eligible third-party Codex Router models into a unified pool."""
    home = Path(target_home).expanduser() if target_home else Path.home()
    native = load_native_codex_supply(home)
    router = load_codex_router_supply(home)

    all_entries: list[UnifiedModelEntry] = []
    slug_to_fam: dict[str, str] = {}
    fam_to_models: dict[str, list[UnifiedModelEntry]] = {}

    # 1. Native eligible models
    if native.available:
        for nm in native.eligible_models:
            entry = UnifiedModelEntry(
                slug=nm.slug,
                display_name=nm.display_name,
                source="native-codex",
                provider="openai",
                route_type="NATIVE",
                model_family=nm.model_family,
                context_window=nm.context_window,
                default_reasoning_effort=nm.default_reasoning_effort,
                reasoning_levels=nm.reasoning_levels,
                supports_vision=nm.supports_vision,
                supports_tools=nm.supports_tools,
                supports_search=nm.supports_search,
            )
            all_entries.append(entry)
            slug_to_fam[entry.slug] = entry.model_family
            fam_to_models.setdefault(entry.model_family, []).append(entry)

    # 2. Router eligible models
    if router.available:
        for rm in router.eligible_models:
            # Prevent duplicate slug if native and router have same slug
            if rm.router_slug in slug_to_fam:
                continue
            entry = UnifiedModelEntry(
                slug=rm.router_slug,
                display_name=rm.display_name,
                source="codex-router",
                provider=rm.provider,
                route_type=rm.route_type,
                model_family=rm.model_family,
                context_window=rm.context_window,
                default_reasoning_effort=rm.default_reasoning_effort,
                reasoning_levels=rm.reasoning_levels,
                supports_vision=rm.supports_vision,
                supports_tools=rm.supports_tools,
                supports_search=rm.supports_search,
            )
            all_entries.append(entry)
            slug_to_fam[entry.slug] = entry.model_family
            fam_to_models.setdefault(entry.model_family, []).append(entry)

    distinct_fams = tuple(sorted(fam_to_models.keys()))
    frozen_fam_map = {k: tuple(v) for k, v in fam_to_models.items()}
    overall_available = native.available or router.available

    return UnifiedModelSupplySnapshot(
        available=overall_available,
        native_supply=native,
        router_supply=router,
        all_eligible_models=tuple(all_entries),
        distinct_families=distinct_fams,
        slug_to_family=slug_to_fam,
        family_to_models=frozen_fam_map,
    )


def _discover_toml_models(source: str, directory: Path, pattern: str) -> DiscoveryResult:
    models: list[str] = []
    invalid_count = 0
    try:
        if not directory.is_dir():
            return DiscoveryResult(source, False, detail="source directory not found")
        paths = sorted(directory.glob(pattern))
        if not paths:
            return DiscoveryResult(source, False, detail="no declaration files found")
        # A matching directory is not a declaration file.  Treat the source as
        # unavailable rather than accidentally reading a non-file path.
        if any(not path.is_file() for path in paths):
            return DiscoveryResult(source, False, detail="source path is not a file")
        for path in paths:
            with path.open("rb") as declaration:
                data = tomllib.load(declaration)
            if not isinstance(data, dict):
                raise ValueError("declaration root is not a table")
            if "model" not in data or data["model"] is None:
                continue
            model = data["model"]
            if not isinstance(model, str) or not model.strip():
                invalid_count += 1
                continue
            if model not in models:
                models.append(model)
    except Exception:
        return DiscoveryResult(source, False, detail="source could not be read")

    if not models and invalid_count > 0:
        return DiscoveryResult(source, False, detail="no valid declarations")

    detail = f"{len(models)} model(s)"
    if invalid_count > 0:
        detail = f"{detail}, {invalid_count} invalid declaration(s)"
    return DiscoveryResult(source, True, tuple(models), detail)


def discover_codex_models(target_home: str | Path, include_unified_supply: bool = False) -> tuple[DiscoveryResult, ...]:
    """Discover declared Codex models and optionally unified model supply (native + router)."""
    home = Path(target_home).expanduser()
    codex_home = home / ".codex"
    
    results: list[DiscoveryResult] = [
        _discover_toml_models("codex-profiles", codex_home, "*.config.toml"),
        _discover_toml_models("codex-agents", codex_home / "agents", "*.toml"),
    ]

    if include_unified_supply:
        try:
            supply: UnifiedModelSupplySnapshot = load_unified_model_supply(home)
            if not supply.available:
                err = supply.native_supply.error or supply.router_supply.error or "unified model supply unavailable"
                results.append(
                    DiscoveryResult("unified-model-supply", False, (), err)
                )
            else:
                eligible_slugs = tuple(m.slug for m in supply.all_eligible_models)
                native_count = len(supply.native_supply.eligible_models)
                router_count = len(supply.router_supply.eligible_models)
                detail = f"{len(eligible_slugs)} eligible model(s) ({native_count} native, {router_count} router across {len(supply.distinct_families)} families)"
                results.append(
                    DiscoveryResult("unified-model-supply", True, eligible_slugs, detail, family_map=supply.slug_to_family)
                )
        except Exception as e:
            results.append(
                DiscoveryResult("unified-model-supply", False, (), f"unified supply could not be loaded: {e}")
            )

    return tuple(results)
