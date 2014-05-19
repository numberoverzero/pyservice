DEFAULT_CONFIG = {
    "protocol": "json",
    "timeout": 2,
    "strict": True
}


def scrub_output(context, whitelist, strict=True):
    r = context.get("response", None)
    if r is None:
        context["response"] = {}
        return
    if not strict:
        return
    context["response"] = {r[k] for k in whitelist}
