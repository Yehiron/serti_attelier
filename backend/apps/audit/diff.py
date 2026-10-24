from collections.abc import Mapping


def compute_diff(
    old: Mapping[str, object], new: Mapping[str, object], *, exclude: tuple[str, ...] = ()
) -> dict[str, list[object]]:
    return {
        field: [old.get(field), new.get(field)]
        for field in old.keys() | new.keys()
        if field not in exclude
        and not any(word in field.lower() for word in ("password", "secret", "token", "key"))
        and old.get(field) != new.get(field)
    }
