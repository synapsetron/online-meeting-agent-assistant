import { useState, useEffect } from "react";
import type { PopupToBackground } from "@/types/messages";

interface AgendaEditItem {
  id: string;
  title: string;
  estimatedMinutes: number;
}

interface Props {
  onClose: () => void;
}

function generateId(): string {
  return `item-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

function createBlankItem(): AgendaEditItem {
  return { id: generateId(), title: "", estimatedMinutes: 5 };
}

export function AgendaEditor({ onClose }: Props) {
  const [items, setItems] = useState<AgendaEditItem[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    chrome.storage.local.get("agendaItems", (result) => {
      if (Array.isArray(result.agendaItems) && result.agendaItems.length > 0) {
        setItems(
          result.agendaItems.map((it: { id: string; title: string; estimatedMinutes?: number }) => ({
            id: it.id,
            title: it.title,
            estimatedMinutes: it.estimatedMinutes ?? 5,
          })),
        );
      } else {
        setItems([createBlankItem()]);
      }
    });
  }, []);

  const addItem = () => setItems([...items, createBlankItem()]);

  const removeItem = (id: string) => {
    const next = items.filter((it) => it.id !== id);
    setItems(next.length > 0 ? next : [createBlankItem()]);
  };

  const updateItem = (id: string, field: keyof AgendaEditItem, value: string | number) => {
    setItems(items.map((it) => (it.id === id ? { ...it, [field]: value } : it)));
  };

  const moveItem = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target], next[index]];
    setItems(next);
  };

  const handleSave = () => {
    const valid = items.filter((it) => it.title.trim().length > 0);
    if (valid.length === 0) return;

    setSaving(true);
    const payload = valid.map((it) => ({
      id: it.id,
      title: it.title.trim(),
      estimatedMinutes: it.estimatedMinutes,
    }));

    chrome.runtime.sendMessage(
      { type: "UPDATE_AGENDA", items: payload } as PopupToBackground,
      () => {
        setSaving(false);
        onClose();
      },
    );
  };

  return (
    <div className="agenda-editor">
      <div className="agenda-editor-header">
        <span className="agenda-editor-title">Edit Agenda</span>
        <button className="agenda-editor-close" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>

      <div className="agenda-editor-list">
        {items.map((item, i) => (
          <div key={item.id} className="agenda-editor-item">
            <div className="agenda-editor-item-order">{i + 1}</div>
            <div className="agenda-editor-item-fields">
              <input
                className="agenda-editor-input"
                type="text"
                value={item.title}
                onChange={(e) => updateItem(item.id, "title", e.target.value)}
                placeholder="Agenda item title..."
                autoFocus={i === items.length - 1 && item.title === ""}
              />
              <div className="agenda-editor-time-row">
                <input
                  className="agenda-editor-time"
                  type="number"
                  min={1}
                  max={120}
                  value={item.estimatedMinutes}
                  onChange={(e) => updateItem(item.id, "estimatedMinutes", Math.max(1, parseInt(e.target.value) || 1))}
                />
                <span className="agenda-editor-time-label">min</span>
              </div>
            </div>
            <div className="agenda-editor-item-actions">
              <button
                className="agenda-editor-move"
                onClick={() => moveItem(i, -1)}
                disabled={i === 0}
                aria-label="Move up"
              >
                ▲
              </button>
              <button
                className="agenda-editor-move"
                onClick={() => moveItem(i, 1)}
                disabled={i === items.length - 1}
                aria-label="Move down"
              >
                ▼
              </button>
              <button
                className="agenda-editor-remove"
                onClick={() => removeItem(item.id)}
                aria-label="Remove item"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>

      <button className="agenda-editor-add" onClick={addItem}>
        + Add item
      </button>

      <div className="agenda-editor-footer">
        <button className="agenda-editor-cancel" onClick={onClose}>
          Cancel
        </button>
        <button
          className="agenda-editor-save"
          onClick={handleSave}
          disabled={saving || items.every((it) => it.title.trim() === "")}
        >
          {saving ? "Saving..." : "Save"}
        </button>
      </div>
    </div>
  );
}
