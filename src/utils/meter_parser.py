"""
Azure OpenAI Meter Name Parser

Parses the wildly inconsistent meter names from the Azure Retail Pricing API
into structured, human-readable components.

Examples:
    "5.1 codex mini cd inp Gl 1M Tokens"  -> GPT-5.1 Codex Mini, Global, Standard, Cached Input
    "gpt-4o-rt-aud-1217 cchd Inp glbl"    -> GPT-4o Realtime Audio (1217), Global, Standard, Cached Input
    "o4-mini 0416 Batch Inp Data Zone"     -> o4-mini (0416), DataZone, Batch, Input
"""

import re
from collections import defaultdict

# --- Normalization Maps ---

DIRECTION_TOKENS = {
    "inp": "Input", "inpt": "Input", "input": "Input", "in": "Input",
    "opt": "Output", "outp": "Output", "output": "Output", "out": "Output",
    "outpt": "Output",
    "training": "Training", "trng": "Training",
    "hosting": "Hosting", "hstng": "Hosting",
}

CACHED_TOKENS = {"cd", "cchd", "cched", "cached", "ccchd"}

DEPLOYMENT_TOKENS = {
    "gl": "Global", "glbl": "Global", "glb": "Global", "global": "Global",
    "dz": "DataZone", "dzone": "DataZone", "datazone": "DataZone", "dzn": "DataZone",
    "regnl": "Regional", "rgnl": "Regional", "regional": "Regional", "regn": "Regional",
}

TIER_TOKENS = {
    "pp": "Provisioned",
    "batch": "Batch",
}

VARIANT_TOKENS = {
    "mini": "Mini", "mn": "Mini", "nano": "Nano", "pro": "Pro", "max": "Max",
}

CAPABILITY_TOKENS = {
    "chat": "Chat", "codex": "Codex",
    "aud": "Audio", "audio": "Audio",
    "rt": "Realtime", "realtime": "Realtime", "rtime": "Realtime",
    "realtimeprvw": "Realtime Preview",
    "img": "Image", "image": "Image",
    "transcribe": "Transcribe", "trscb": "Transcribe", "tcrb": "Transcribe",
    "tts": "TTS",
}

MEDIA_TOKENS = {"txt": "Text", "aud": "Audio", "audio": "Audio", "img": "Image", "image": "Image"}

# Tokens to strip (unit suffixes)
UNIT_SUFFIXES = {"tokens", "token", "1m", "1k", "unit", "units", "session",
                 "images", "gb", "characters", "calls", "second", "deployment", "ep"}

# Special non-model meters (infrastructure/platform)
SPECIAL_METERS = {
    "assistants-file search": "Assistants File Search",
    "code-interpreter": "Code Interpreter",
    "file-search-tool-calls": "File Search Tool Calls",
    "provisioned managed": "Provisioned Managed",
    "provisioned throughput": "Provisioned Throughput",
}


def parse_meter(meter_name, sku_name="", product_name=""):
    """
    Parse a raw Azure meter name into structured pricing components.

    Args:
        meter_name: The meterName field from Azure Pricing API
        sku_name: The skuName field (sometimes cleaner)
        product_name: The productName field (hints at model family)

    Returns dict with keys:
        model, variant, version, capability, deployment, tier, direction,
        media_type, display_name, group_key
    """
    result = {
        "model": "", "variant": "", "version": "", "capability": "",
        "deployment": "", "tier": "Standard", "direction": "",
        "media_type": "", "display_name": "", "group_key": "",
    }

    original = meter_name.strip()
    if not original:
        result["display_name"] = result["group_key"] = "(empty)"
        return result

    # Check for special/infrastructure meters
    lower = original.lower()
    for prefix, name in SPECIAL_METERS.items():
        if lower.startswith(prefix):
            result["model"] = name
            # Extract deployment
            for tok, deploy in DEPLOYMENT_TOKENS.items():
                if tok in lower:
                    result["deployment"] = deploy
                    break
            result["display_name"] = result["group_key"] = name
            return result

    # Handle specific edge cases
    if lower.startswith("az-"):
        return _parse_legacy_az(original, result)
    if lower.startswith("image-dall"):
        return _parse_dalle(original, result)
    if lower.startswith("sora"):
        return _parse_sora(original, result)
    if lower.startswith("embedding-ada") or lower.startswith("text-embedding") or lower.startswith("text embedding"):
        return _parse_embedding(original, result)
    if lower.startswith("gpt-oss") or lower.startswith("oss-"):
        return _parse_oss(original, result)
    if lower.startswith("computer-use"):
        return _parse_simple_model(original, "Computer Use", result)

    # Main parsing: determine model family from product_name hint
    product_lower = product_name.lower() if product_name else ""

    if "pp gpt4" in product_lower:
        return _parse_pp_gpt4(original, result)
    elif "gpt5" in product_lower:
        return _parse_gpt5_product(original, result)
    elif "reasoning" in product_lower:
        return _parse_reasoning(original, result)
    elif "media" in product_lower:
        return _parse_media(original, result)
    elif "embedding" in product_lower:
        return _parse_embedding(original, result)
    elif "oss" in product_lower:
        return _parse_oss(original, result)
    else:
        # Azure OpenAI (main product) — broadest category
        return _parse_main_openai(original, result)


def _tokenize(text):
    """Split meter name into normalized tokens, stripping unit suffixes."""
    # Replace hyphens with spaces for splitting, but preserve key patterns
    # First handle known hyphenated model names
    normalized = text

    # Strip trailing unit tokens
    tokens = normalized.split()
    # Remove unit suffix tokens from end
    while tokens and tokens[-1].lower() in UNIT_SUFFIXES:
        tokens.pop()
    # Also remove "1M", "1K" etc from anywhere
    tokens = [t for t in tokens if t.lower() not in UNIT_SUFFIXES]
    return tokens


def _extract_attributes(tokens, result):
    """Extract deployment, tier, direction, cached, variant, version, capability from tokens."""
    remaining = []
    i = 0
    while i < len(tokens):
        tok = tokens[i].lower().rstrip("-")

        # Multi-token: "Data Zone"
        if tok == "data" and i + 1 < len(tokens) and tokens[i + 1].lower() in ("zone", "zone,"):
            result["deployment"] = "DataZone"
            i += 2
            continue

        # Multi-token: "high res"
        if tok == "high" and i + 1 < len(tokens) and tokens[i + 1].lower() == "res":
            remaining.append("HighRes")
            i += 2
            continue

        # Multi-token: model ft grader / mdl grdr
        if tok in ("model", "mdl", "mdel") and i + 1 < len(tokens) and tokens[i + 1].lower() in ("grader", "grdr"):
            result["tier"] = "FT Grader"
            i += 2
            continue

        # Multi-token: "deep research"
        if tok == "deep" and i + 1 < len(tokens) and tokens[i + 1].lower() == "research":
            result["capability"] = "Deep Research"
            i += 2
            continue

        # Cached tokens (look-ahead: next token is direction)
        if tok in CACHED_TOKENS:
            # Mark as cached, direction will be set later
            result["_cached"] = True
            i += 1
            continue

        # Deployment
        if tok in DEPLOYMENT_TOKENS and not result["deployment"]:
            result["deployment"] = DEPLOYMENT_TOKENS[tok]
            i += 1
            continue

        # Tier
        if tok in TIER_TOKENS:
            result["tier"] = TIER_TOKENS[tok]
            i += 1
            continue

        # Fine-tuning indicators
        if tok in ("ft", "ft-"):
            if result["tier"] == "Standard":
                result["tier"] = "Fine-tuning"
            i += 1
            continue

        if tok == "rft":
            result["tier"] = "RFT"
            i += 1
            continue

        if tok == "dev" and i + 1 < len(tokens) and tokens[i + 1].lower() in ("ft", "rft"):
            result["tier"] = f"Dev {tokens[i + 1].upper()}"
            i += 2
            continue

        # Direction
        if tok in DIRECTION_TOKENS:
            result["direction"] = DIRECTION_TOKENS[tok]
            i += 1
            continue

        # Variant
        if tok in VARIANT_TOKENS and not result["variant"]:
            result["variant"] = VARIANT_TOKENS[tok]
            i += 1
            continue

        # Version (4-digit date codes or decimal versions like 1.5)
        if re.match(r'^\d+\.\d+$', tok) and not result["version"]:
            result["version"] = tok
            i += 1
            continue
        if re.match(r'^\d{4}$', tok) and not result["version"]:
            result["version"] = tok
            i += 1
            continue

        # Capability (including combined tokens like "aud1217", "txt1217")
        if tok in CAPABILITY_TOKENS and not result["capability"]:
            result["capability"] = CAPABILITY_TOKENS[tok]
            i += 1
            continue
        # Combined capability+version: "aud1217", "txt1217"
        cap_ver = re.match(r'^(aud|txt|img)(\d{4})$', tok)
        if cap_ver and not result["capability"]:
            result["capability"] = CAPABILITY_TOKENS.get(cap_ver.group(1), cap_ver.group(1))
            if not result["version"]:
                result["version"] = cap_ver.group(2)
            i += 1
            continue

        # Media type
        if tok in MEDIA_TOKENS and not result.get("media_type"):
            # If capability not set and this is a media-type-as-capability token, set capability
            if not result.get("capability") and tok in CAPABILITY_TOKENS:
                result["capability"] = CAPABILITY_TOKENS[tok]
            else:
                result["media_type"] = MEDIA_TOKENS[tok]
            i += 1
            continue

        # "d" prefix in media context (e.g., "tcrb d aud" = transcribe audio)
        if tok == "d" and i + 1 < len(tokens) and tokens[i + 1].lower() in MEDIA_TOKENS:
            # skip "d", next iteration handles media type
            i += 1
            continue

        # "prvw" = preview (modifier, not standalone)
        if tok == "prvw":
            i += 1
            continue

        remaining.append(tokens[i])
        i += 1

    # Apply cached flag
    if result.pop("_cached", False):
        if result["direction"] == "Input" or not result["direction"]:
            result["direction"] = "Cached Input"
        elif result["direction"] == "":
            result["direction"] = "Cached Input"

    return remaining


def _finalize(result):
    """Build display_name and group_key from parsed components."""
    # Deduplicate: if capability is already embedded in model name, clear it
    model_lower = result["model"].lower()
    if result["capability"]:
        cap_lower = result["capability"].lower()
        if cap_lower in model_lower:
            result["capability"] = ""

    parts = [result["model"]]
    if result["capability"] and result["capability"] not in ("Chat",):
        parts.append(result["capability"])
    if result["variant"]:
        parts.append(result["variant"])

    result["group_key"] = " ".join(parts)

    display_parts = list(parts)
    if result["version"]:
        display_parts.append(f"({result['version']})")

    label_parts = []
    if result["deployment"]:
        label_parts.append(result["deployment"])
    if result["tier"] != "Standard":
        label_parts.append(result["tier"])
    if result["direction"]:
        label_parts.append(result["direction"])
    if result["media_type"]:
        label_parts.append(f"[{result['media_type']}]")

    if label_parts:
        result["display_name"] = " ".join(display_parts) + " — " + " / ".join(label_parts)
    else:
        result["display_name"] = " ".join(display_parts)

    return result


def _parse_gpt5_product(original, result):
    """Parse meters under 'Azure OpenAI GPT5' product.
    These start with version number (5, 5.1, 5.2, etc.) or 'GPT 5' or 'gpt 5' or 'gpt-5'."""
    tokens = _tokenize(original)
    if not tokens:
        result["display_name"] = result["group_key"] = original
        return result

    tok0 = tokens[0].lower()

    # Handle "GPT" prefix: "GPT 5", "GPT 5.1", etc.
    if tok0 == "gpt" and len(tokens) > 1:
        version_tok = tokens[1]
        if re.match(r'^5(\.\d+)?$', version_tok):
            result["model"] = f"GPT-{version_tok}"
            tokens = tokens[2:]
        else:
            result["model"] = "GPT-5"
            tokens = tokens[1:]
    # Handle "gpt-5-codex" style
    elif tok0.startswith("gpt-5"):
        m = re.match(r'gpt-(\d+\.?\d*)', tok0)
        if m:
            result["model"] = f"GPT-{m.group(1)}"
            # Check for codex etc in remaining hyphenated parts
            rest = tok0[m.end():]
            if rest.startswith("-"):
                extra_tokens = rest[1:].split("-")
                tokens = extra_tokens + tokens[1:]
            else:
                tokens = tokens[1:]
        else:
            result["model"] = "GPT-5"
            tokens = tokens[1:]
    # Handle "gpt 5 ..." style
    elif tok0 == "gpt" or tok0.startswith("gpt"):
        if len(tokens) > 1 and re.match(r'^5(\.\d+)?$', tokens[1]):
            result["model"] = f"GPT-{tokens[1]}"
            tokens = tokens[2:]
        else:
            result["model"] = "GPT-5"
            tokens = tokens[1:]
    # Bare version: "5.1 codex ..."
    elif re.match(r'^5(\.\d+)?$', tok0):
        result["model"] = f"GPT-{tok0}"
        tokens = tokens[1:]
    else:
        result["model"] = "GPT-5"

    _extract_attributes(tokens, result)
    return _finalize(result)


def _parse_pp_gpt4(original, result):
    """Parse meters under 'Azure OpenAI PP GPT4s' product.
    Provisioned pricing for GPT-4 series. Patterns: '4.1 pp cd inp Gl', 'gpt 41 mn pp inp glb'."""
    tokens = _tokenize(original)
    result["tier"] = "Provisioned"

    tok0 = tokens[0].lower() if tokens else ""

    if tok0 == "gpt" and len(tokens) > 1:
        # "gpt 41 mn pp ..." -> GPT-4.1
        version_str = tokens[1]
        if re.match(r'^\d+$', version_str) and len(version_str) == 2:
            # "41" -> "4.1"
            result["model"] = f"GPT-{version_str[0]}.{version_str[1]}"
        else:
            result["model"] = f"GPT-{version_str}"
        tokens = tokens[2:]
    elif re.match(r'^\d+\.?\d*$', tok0):
        result["model"] = f"GPT-{tok0}"
        tokens = tokens[1:]
    else:
        result["model"] = "GPT-4"

    _extract_attributes(tokens, result)
    return _finalize(result)


def _parse_reasoning(original, result):
    """Parse meters under 'Azure OpenAI Reasoning' product.
    o-series, codex mini, o3-deep research, etc."""
    tokens = _tokenize(original)
    tok0 = tokens[0].lower() if tokens else ""

    # Handle hyphenated o-series: o1-pro, o3-pro, o4-mini, o3-ft, o3-mini-ft, o3-deep
    if tok0.startswith("o") and re.match(r'^o\d', tok0):
        # Split on hyphens
        parts = tokens[0].split("-")
        result["model"] = parts[0]  # o1, o3, o4
        extra = parts[1:]
        # Check for variant and tier in hyphenated parts
        remaining_extra = []
        for p in extra:
            pl = p.lower()
            if pl in VARIANT_TOKENS and not result["variant"]:
                result["variant"] = VARIANT_TOKENS[pl]
            elif pl in ("ft",):
                result["tier"] = "Fine-tuning"
            elif pl == "deep":
                remaining_extra.append(p)
            else:
                remaining_extra.append(p)
        tokens = remaining_extra + tokens[1:]
    # Handle "codex mini" (under Reasoning = codex-mini reasoning model)
    elif tok0 == "codex":
        result["model"] = "Codex Mini"
        if len(tokens) > 1 and tokens[1].lower() == "mini":
            tokens = tokens[2:]
        else:
            tokens = tokens[1:]
    else:
        result["model"] = tokens[0]
        tokens = tokens[1:]

    _extract_attributes(tokens, result)
    return _finalize(result)


def _parse_media(original, result):
    """Parse meters under 'Azure OpenAI Media' product.
    GPT audio, realtime, image, transcribe, TTS, Sora models."""
    tokens = _tokenize(original)
    if not tokens:
        result["display_name"] = result["group_key"] = original
        return result

    tok0 = tokens[0].lower()

    # Sora
    if tok0 == "sora":
        return _parse_sora(original, result)

    # "gpt4o" or "gpt4omini" compact forms
    if tok0.startswith("gpt4o"):
        if "mini" in tok0:
            result["model"] = "GPT-4o"
            result["variant"] = "Mini"
        else:
            result["model"] = "GPT-4o"
        # Handle hyphenated suffixes: gpt4omini-rt-aud1217, gpt4o-mn-trscb
        rest = tokens[0]
        # Strip model prefix
        if tok0.startswith("gpt4omini"):
            rest = rest[9:]  # after "gpt4omini"
        else:
            rest = rest[5:]  # after "gpt4o"
        extra = [t for t in rest.split("-") if t] if rest.startswith("-") else []
        tokens = extra + tokens[1:]
        _extract_attributes(tokens, result)
        return _finalize(result)

    # "gpt" prefix: gpt aud, gpt rt, gpt img, gpt 4o tcrb
    if tok0 == "gpt":
        tokens = tokens[1:]
        # Check if next token is model version like "4o"
        if tokens and re.match(r'^\d', tokens[0].lower()):
            result["model"] = f"GPT-{tokens[0]}"
            tokens = tokens[1:]
        else:
            result["model"] = "GPT"
        _extract_attributes(tokens, result)
        # If model is just "GPT", fold capability into model name to avoid "GPT Audio Audio"
        if result["model"] == "GPT" and result["capability"]:
            cap = result["capability"]
            result["model"] = f"GPT {cap}"
            result["capability"] = ""  # Already in model name
        return _finalize(result)

    # gpt-image-1, gpt-4o-* hyphenated
    if tok0.startswith("gpt-"):
        return _parse_main_openai(original, result)

    # Fallback
    _extract_attributes(tokens, result)
    result["model"] = result["model"] or tokens[0] if tokens else "Unknown"
    return _finalize(result)


def _parse_main_openai(original, result):
    """Parse meters under main 'Azure OpenAI' product.
    Covers GPT-4o, GPT-4.1, GPT-3.5, GPT-4, o-series, embeddings, etc."""
    # First try to handle hyphenated prefixes
    tokens_raw = _tokenize(original)
    if not tokens_raw:
        result["display_name"] = result["group_key"] = original
        return result

    first = tokens_raw[0]
    first_lower = first.lower()

    # --- Hyphenated model names ---
    # gpt-4o-mini-0718-Batch-Inp-glbl, gpt-4.1-mini-ft, gpt-35-turbo-16k
    if first_lower.startswith("gpt-") or first_lower.startswith("gpt4o"):
        return _parse_hyphenated_gpt(original, result)

    # o-series: o1, o3, o4-mini
    if re.match(r'^o\d', first_lower):
        return _parse_reasoning(original, result)

    # "gpt 4.1 mini ...", "gpt 4o 0513 ..."
    if first_lower == "gpt" and len(tokens_raw) > 1:
        next_tok = tokens_raw[1].lower()
        # "gpt 4.1", "gpt 4o"
        if re.match(r'^4', next_tok) or re.match(r'^\d', next_tok):
            model_str = tokens_raw[1]
            # Normalize: "4.1" stays, "4o" stays
            result["model"] = f"GPT-{model_str}"
            tokens = tokens_raw[2:]
            _extract_attributes(tokens, result)
            return _finalize(result)

    # text-embedding, embedding-ada
    if "embedding" in first_lower:
        return _parse_embedding(original, result)

    # computer-use
    if first_lower.startswith("computer"):
        return _parse_simple_model(original, "Computer Use", result)

    # file-search-tool-calls
    if first_lower.startswith("file-search"):
        return _parse_simple_model(original, "File Search Tool Calls", result)

    # Fallback: use tokens as-is
    tokens = tokens_raw
    _extract_attributes(tokens, result)
    if not result["model"]:
        result["model"] = " ".join(tokens) if tokens else original
    return _finalize(result)


def _parse_hyphenated_gpt(original, result):
    """Parse hyphenated GPT model names like gpt-4o-mini-0718-Batch-Inp-glbl."""
    # Split entire string on spaces first, then handle hyphens in model prefix
    tokens = _tokenize(original)
    first = tokens[0]

    # Try to extract model from the hyphenated first token
    # Patterns: gpt-4o, gpt-4o-mini, gpt-4o-0806, gpt-4.1, gpt-4.1-mini, gpt-35-turbo
    # gpt-4-turbo, gpt-4-8K, gpt-image-1, gpt-4o-aud-0603, gpt-4o-rt-txt-1217
    parts = first.split("-")
    # parts[0] = "gpt" (or "gpt4o", "gpt4omini")

    if parts[0].lower() == "gpt4omini":
        result["model"] = "GPT-4o"
        result["variant"] = "Mini"
        model_parts_consumed = 1
    elif parts[0].lower() == "gpt4o":
        result["model"] = "GPT-4o"
        model_parts_consumed = 1
    elif parts[0].lower() == "gpt" and len(parts) > 1:
        model_id = parts[1]

        # gpt-35-turbo
        if model_id == "35":
            result["model"] = "GPT-3.5-Turbo"
            model_parts_consumed = 2
            if len(parts) > 2 and parts[2].lower() in ("turbo", "trb16k"):
                model_parts_consumed = 3
        # gpt-4-turbo, gpt-4-8K, gpt-4-32K
        elif model_id == "4" and len(parts) > 2 and parts[2].lower() in ("turbo", "turbo128k", "8k", "32k"):
            ctx = parts[2]
            result["model"] = f"GPT-4-{ctx}"
            model_parts_consumed = 3
        # gpt-4o, gpt-4.1, gpt-5
        elif re.match(r'^[45]\w*', model_id):
            result["model"] = f"GPT-{model_id}"
            model_parts_consumed = 2
            # Check for variant: gpt-4o-mini, gpt-4.1-mini, gpt-4.1-nano
            if len(parts) > 2 and parts[2].lower() in VARIANT_TOKENS:
                result["variant"] = VARIANT_TOKENS[parts[2].lower()]
                model_parts_consumed = 3
        # gpt-image-1
        elif model_id.lower() == "image":
            version = parts[2] if len(parts) > 2 else ""
            result["model"] = f"GPT-Image-{version}" if version else "GPT-Image"
            model_parts_consumed = 3 if version else 2
        # gpt-oss
        elif model_id.lower() == "oss":
            return _parse_oss(original, result)
        else:
            result["model"] = f"GPT-{model_id}"
            model_parts_consumed = 2
    else:
        result["model"] = parts[0]
        model_parts_consumed = 1

    # Remaining hyphenated parts become tokens
    remaining_parts = parts[model_parts_consumed:]
    # Rejoin with the rest of space-separated tokens
    extra_tokens = []
    for p in remaining_parts:
        if p:
            extra_tokens.append(p)
    extra_tokens.extend(tokens[1:])

    _extract_attributes(extra_tokens, result)
    return _finalize(result)


def _parse_legacy_az(original, result):
    """Parse 'Az-' prefixed legacy meters."""
    # Strip 'Az-' prefix
    stripped = original[3:]
    tokens = _tokenize(stripped)
    if tokens:
        # Usually "GPT-3.5-turbo", "GPT4-Turbo-128K", "Provisioned Throughput"
        if tokens[0].lower().startswith("gpt"):
            result["model"] = tokens[0]
            tokens = tokens[1:]
        elif tokens[0].lower() == "provisioned":
            result["model"] = "Provisioned Throughput"
            result["display_name"] = result["group_key"] = "Provisioned Throughput"
            return result
        _extract_attributes(tokens, result)
    result["model"] = result["model"] or stripped
    return _finalize(result)


def _parse_dalle(original, result):
    """Parse DALL-E meters."""
    result["model"] = "DALL-E"
    tokens = _tokenize(original)
    # Extract version and quality info
    for tok in tokens:
        tl = tok.lower()
        if tl in ("2", "3"):
            result["version"] = tok
        elif tl in ("hd", "std"):
            result["variant"] = tok.upper()
        elif tl in ("highres", "lowres"):
            result["media_type"] = tok
        elif tl in DEPLOYMENT_TOKENS:
            result["deployment"] = DEPLOYMENT_TOKENS[tl]
    if result["version"]:
        result["model"] = f"DALL-E-{result['version']}"
        result["version"] = ""
    return _finalize(result)


def _parse_sora(original, result):
    """Parse Sora meters."""
    tokens = _tokenize(original)
    result["model"] = "Sora"
    remaining = []
    for tok in tokens:
        tl = tok.lower()
        if tl == "sora":
            continue
        elif tl == "2":
            result["model"] = "Sora 2"
        elif tl in VARIANT_TOKENS:
            result["variant"] = VARIANT_TOKENS[tl]
        elif tl in DEPLOYMENT_TOKENS:
            result["deployment"] = DEPLOYMENT_TOKENS[tl]
        elif tl in ("high", "res"):
            remaining.append(tok)
    return _finalize(result)


def _parse_embedding(original, result):
    """Parse embedding meters."""
    tokens = _tokenize(original)
    first_lower = tokens[0].lower() if tokens else ""

    if "embedding-ada" in first_lower or (first_lower == "embedding" and len(tokens) > 1):
        result["model"] = "Embedding Ada"
    elif "text-embedding-3" in first_lower or "text embedding 3" in " ".join(t.lower() for t in tokens[:3]):
        # Find size
        full = " ".join(t.lower() for t in tokens)
        if "large" in full:
            result["model"] = "Text-Embedding-3-Large"
        elif "small" in full:
            result["model"] = "Text-Embedding-3-Small"
        else:
            result["model"] = "Text-Embedding-3"
    else:
        result["model"] = "Embedding"

    for tok in tokens:
        tl = tok.lower()
        if tl in DEPLOYMENT_TOKENS:
            result["deployment"] = DEPLOYMENT_TOKENS[tl]
        elif tl == "grader":
            result["tier"] = "FT Grader"

    return _finalize(result)


def _parse_oss(original, result):
    """Parse OSS (open source) model meters."""
    tokens = _tokenize(original)
    full = " ".join(tokens).lower()
    if "120b" in full:
        result["model"] = "OSS-120B"
    elif "20b" in full:
        result["model"] = "OSS-20B"
    else:
        result["model"] = "OSS"

    for tok in tokens:
        tl = tok.lower()
        if tl in DEPLOYMENT_TOKENS:
            result["deployment"] = DEPLOYMENT_TOKENS[tl]
        if tl in DIRECTION_TOKENS:
            result["direction"] = DIRECTION_TOKENS[tl]
        if tl in ("ft", "ft-"):
            result["tier"] = "Fine-tuning"

    return _finalize(result)


def _parse_simple_model(original, model_name, result):
    """Parse a simple model with standard attribute extraction."""
    result["model"] = model_name
    tokens = _tokenize(original)
    # Skip tokens that are part of the model name
    model_tokens = model_name.lower().split()
    skip = 0
    for i, tok in enumerate(tokens):
        if i < len(model_tokens) and tok.lower().replace("-", " ").startswith(model_tokens[i][:3]):
            skip = i + 1
    tokens = tokens[skip:]
    _extract_attributes(tokens, result)
    return _finalize(result)


def group_pricing(items):
    """
    Group a flat list of enriched pricing items into a nested structure.

    Args:
        items: list of dicts, each containing at minimum:
            'Price', 'group_key', 'deployment', 'tier', 'direction'
            (as returned by parse_meter + fetch_pricing_as_list)

    Returns:
        {
            "GPT-5.1": {
                "Global": {
                    "Standard": {"Input": price, "Cached Input": price, "Output": price},
                    "Provisioned": {...},
                },
                "DataZone": {...},
            },
            ...
        }
    """
    grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

    for item in items:
        group = item.get("group_key", "Unknown")
        deployment = item.get("deployment", "Unknown")
        tier = item.get("tier", "Standard")
        direction = item.get("direction", "Other")
        price = item.get("Price", "N/A")

        if deployment and direction:
            grouped[group][deployment][tier][direction] = price

    # Convert defaultdicts to regular dicts
    return {k: {dk: {tk: dict(tv) for tk, tv in dv.items()} for dk, dv in v.items()} for k, v in grouped.items()}


def format_grouped_pricing_text(grouped):
    """Format grouped pricing as readable plain text."""
    lines = []
    for model in sorted(grouped.keys()):
        lines.append(f"\n{'='*60}")
        lines.append(f"  {model}")
        lines.append(f"{'='*60}")

        deployments = grouped[model]
        for deployment in sorted(deployments.keys()):
            tiers = deployments[deployment]
            for tier in sorted(tiers.keys()):
                directions = tiers[tier]
                header = f"  {deployment}"
                if tier != "Standard":
                    header += f" / {tier}"
                lines.append(header)

                for direction in ["Input", "Cached Input", "Output", "Training", "Hosting"]:
                    if direction in directions:
                        price = directions[direction]
                        if isinstance(price, (int, float)):
                            lines.append(f"    {direction:15s}  ${price:.6f}")
                        else:
                            lines.append(f"    {direction:15s}  {price}")

                # Any remaining directions
                for direction, price in sorted(directions.items()):
                    if direction not in ("Input", "Cached Input", "Output", "Training", "Hosting"):
                        if isinstance(price, (int, float)):
                            lines.append(f"    {direction:15s}  ${price:.6f}")
                        else:
                            lines.append(f"    {direction:15s}  {price}")

    return "\n".join(lines)
