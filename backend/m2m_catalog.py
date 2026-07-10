"""
Introspection du catalogue M2M d'une application.

Fournit :
- deduce_auth_level(route) : niveau d'auth d'une route FastAPI
- resolve_refs(spec) : résolution des $ref OpenAPI (inlining + détection de cycles)
- build_app_catalog(app) : catalogue structuré d'une app

Aucune dépendance réseau : l'app ne se décrit qu'elle-même.
"""
from typing import Any, Iterator
from hub_auth import get_current_user


def _walk_deps(dependant: Any) -> Iterator[Any]:
    """Parcourt récursivement l'arbre des dépendances FastAPI d'un dependant."""
    for dep in getattr(dependant, "dependencies", []) or []:
        yield dep
        yield from _walk_deps(dep)


def deduce_auth_level(route: Any) -> str:
    """
    Déduit le niveau d'auth d'une route en inspectant ses dépendances.

    Règle de priorité (premier match gagne) :
      1. __auth_level__ == "service"  -> "service" (court-circuit, priorité max)
      2. __auth_level__ présent        -> cette valeur (viewer/user/manager/admin)
      3. présence de get_current_user  -> "user"
      4. sinon                         -> "public"
    """
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return "public"

    found_role = None
    found_user = False

    for dep in _walk_deps(dependant):
        call = getattr(dep, "call", None)
        if call is None:
            continue
        level = getattr(call, "__auth_level__", None)
        if level == "service":
            return "service"  # priorité maximale, on court-circuite
        if level is not None and found_role is None:
            found_role = level
        if call is get_current_user or getattr(call, "__name__", "") == "get_current_user":
            found_user = True

    if found_role:
        return found_role
    if found_user:
        return "user"
    return "public"


HTTP_METHODS = ("get", "post", "put", "delete", "patch")


def resolve_refs(spec: dict) -> dict:
    """
    Résout les $ref d'un spec OpenAPI en inlinant les références vers
    #/components/schemas/*. Détecte les cycles (remplace par {"$ref_circular": name}).

    Retourne {"paths": {...}, "components_raw": {...}} où toutes les opérations
    HTTP ont leurs schémas inlinés.
    """
    components = spec.get("components", {}).get("schemas", {})

    def resolve(node: Any, visiting: set) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]
                ref_name = ref_path.split("/")[-1]
                if ref_name in visiting:
                    return {"$ref_circular": ref_name}
                target = components.get(ref_name)
                if target is None:
                    return {"$ref_unresolved": ref_path}
                return resolve(target, visiting | {ref_name})
            return {k: resolve(v, visiting) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(item, visiting) for item in node]
        return node

    resolved_paths = {}
    for path, methods in spec.get("paths", {}).items():
        resolved_paths[path] = {}
        for method, op in methods.items():
            if method in HTTP_METHODS:
                resolved_paths[path][method] = resolve(op, set())

    return {"paths": resolved_paths, "components_raw": components}


# Routes techniques à exclure du catalogue (bruit pour l'IA).
EXCLUDED_PATHS = {
    "/docs", "/redoc", "/openapi.json", "/api/openapi.json",
    "/api/m2m/catalog",  # auto-référence
}


def _extract_request_body(op: dict) -> dict | None:
    rb = op.get("requestBody")
    if not rb:
        return None
    json_media = rb.get("content", {}).get("application/json", {})
    return {
        "required": rb.get("required", False),
        "content_type": "application/json",
        "schema": json_media.get("schema"),
    }


def _extract_responses(op: dict) -> dict:
    out = {}
    for code, resp in op.get("responses", {}).items():
        out[code] = {
            "description": resp.get("description", ""),
            "schema": resp.get("content", {}).get("application/json", {}).get("schema"),
        }
    return out


def _extract_params(op: dict):
    path_params, query_params = [], []
    for p in op.get("parameters", []):
        entry = {
            "name": p.get("name"),
            "required": p.get("required", False),
            "schema": p.get("schema", {}),
        }
        if p.get("in") == "path":
            path_params.append(entry)
        elif p.get("in") == "query":
            query_params.append(entry)
    return path_params, query_params


def build_app_catalog(
    app,
    slug: str | None = None,
    name: str | None = None,
    description: str | None = None,
    version: str | None = None,
) -> dict:
    """
    Construit le catalogue M2M d'une app FastAPI.

    1. Génère l'OpenAPI (paths, méthodes, summaries, schémas).
    2. Mappe chaque (path, method) -> auth_level via introspection des Depends.
    3. Résout les $ref (inlining).
    4. Retourne un dict structuré.
    """
    spec = app.openapi()
    resolved = resolve_refs(spec)

    # Carte (path, method_lower) -> auth_level
    auth_map: dict[tuple[str, str], str] = {}
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        level = deduce_auth_level(route)
        for m in methods:
            auth_map[(path, m.lower())] = level

    endpoints = []
    for path, methods in resolved["paths"].items():
        if path in EXCLUDED_PATHS:
            continue
        for method, op in methods.items():
            if method not in HTTP_METHODS:
                continue
            path_params, query_params = _extract_params(op)
            endpoints.append({
                "path": path,
                "method": method.upper(),
                "summary": op.get("summary"),
                "description": op.get("description"),
                "auth_level": auth_map.get((path, method), "public"),
                "tags": op.get("tags", []),
                "path_params": path_params,
                "query_params": query_params,
                "request_body": _extract_request_body(op),
                "responses": _extract_responses(op),
            })

    return {
        "slug": slug,
        "name": name,
        "description": description,
        "version": version,
        "is_shared": None,  # renseigné par le Hub lors de l'agrégation
        "introspection_source": "m2m-catalog",
        "endpoints": endpoints,
    }
