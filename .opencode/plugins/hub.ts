// SPDX-License-Identifier: MIT
// Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

/**
 * Plugin Hub - outillage opencode pour le Hub et les apps generees depuis
 * HUBapp_TEMPLATE_base. Accompagne le MCP `hub` (hub_mcp/server.py).
 *
 * Source de verite : POULIDOR/.opencode/plugins/hub.ts
 * Copie template synchronisee via `make sync-hub-tooling` (verif : `make sync-hub-tooling-check`).
 *
 * API plugins OpenCode V2 : le PluginSupervisor exige un export par defaut
 * `{ id, setup }` (l'ancien format V1 - fonction exportee + hook string
 * "permission.asked" - n'est plus charge, cf. incident "skills indisponibles"
 * du 05/10/2026). Le hook V2 equivalent est ctx.permission.hook("evaluate").
 *
 * Garde-fou : pour les operations destructrices (suppression Hub, restore,
 * revocation, prod, rm -rf, down -v, push --force...), on ne fait JAMAIS
 * confiance a un "allow" automatique : on retrograde la decision en "ask".
 * On ne deny jamais et on n'allow jamais de soi-meme.
 */
const DESTRUCTIVE = [
  /\bhub_\w*_delete\b/i,
  /\bhub_backup_restore\b/i,
  /\bhub_app_(delete|approve|toggle_active)\b/i,
  /\brm\s+-[a-z]*r[a-z]*f/i,
  /docker\s+compose\s+down\s+.*(-v|--volumes)/i,
  /\bDELETE_DATA\b/i,
  /\bdrop\s+database\b/i,
  /git\s+push\s+.*--force/i,
  /\bclean-all\b/i,
  /\b(prod|production)\b.*\b(deploy|up|down|restart)\b/i,
]

/**
 * Decision de permission V2 (PermissionEvaluation) : le hook "evaluate" est
 * appele pour les decisions "allow" et "ask" ; un "deny" explicite (regle
 * configuree) est final et n'atteint jamais le hook. Seuls `effect` et
 * `message` sont mutables.
 */
interface PermissionEvaluation {
  readonly action: string
  readonly resources: readonly string[]
  readonly metadata?: Record<string, unknown>
  effect: "allow" | "ask" | "deny"
  message?: string
}

/** Sous-ensemble du contexte plugin V2 utilise ici (typage structurel local,
 * sans dependance a @opencode/plugin non installe localement). */
interface HubGuardContext {
  permission: {
    hook(
      name: "evaluate",
      callback: (event: PermissionEvaluation) => Promise<void> | void,
    ): Promise<unknown>
  }
}

export default {
  id: "hub.guard",
  async setup(ctx: HubGuardContext) {
    await ctx.permission.hook("evaluate", (event) => {
      try {
        // On ne retrograde qu'un "allow" automatique ; un "ask" reste "ask".
        if (event.effect !== "allow") return
        const parts: string[] = [event.action, ...event.resources]
        if (event.metadata) parts.push(JSON.stringify(event.metadata))
        const haystack = parts.filter(Boolean).join(" ")
        if (DESTRUCTIVE.some((re) => re.test(haystack))) {
          event.effect = "ask"
          event.message =
            "Operation destructive detectee (garde-fou hub) : validation humaine requise."
        }
      } catch {
        // Le garde-fou ne doit jamais casser le pipeline de permissions.
        return
      }
    })
  },
}
