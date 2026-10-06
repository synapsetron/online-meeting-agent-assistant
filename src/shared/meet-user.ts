const GENERIC_SELF_LABELS = new Set(["you", "ви", "вы", "me", "я"]);

function cleanName(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const name = raw.replace(/\s+/g, " ").replace(/\(.*?\)/g, "").trim();
  if (!name || name.length > 60 || GENERIC_SELF_LABELS.has(name.toLowerCase())) return null;
  return name;
}

function nameFromAccountButton(): string | null {
  const candidates = document.querySelectorAll(
    'a[aria-label^="Google Account"], a[aria-label^="Обліковий запис Google"], a[aria-label^="Аккаунт Google"], [aria-label^="Google Account"]',
  );
  for (const el of candidates) {
    const label = el.getAttribute("aria-label") || "";
    const afterColon = label.split(":").slice(1).join(":");
    const name = cleanName(afterColon.split("\n")[0]);
    if (name) return name;
  }
  return null;
}

function nameFromSelfTile(): string | null {
  for (const el of document.querySelectorAll("[data-self-name]")) {
    const name = cleanName(el.getAttribute("data-self-name"));
    if (name) return name;
  }
  return null;
}

async function nameFromSettings(): Promise<string | null> {
  try {
    const result = await chrome.storage.local.get("userName");
    return cleanName(result.userName as string | undefined);
  } catch {
    return null;
  }
}

/**
 * Resolve the local user's display name: explicit setting wins,
 * then Meet DOM (self tile, Google account button). Returns null if unknown.
 */
export async function resolveLocalUserName(): Promise<string | null> {
  return (await nameFromSettings()) ?? nameFromSelfTile() ?? nameFromAccountButton();
}
