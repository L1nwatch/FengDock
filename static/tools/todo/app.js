const form = document.getElementById("todo-form");
const titleInput = document.getElementById("todo-title");
const notesInput = document.getElementById("todo-notes");
const pendingList = document.getElementById("todo-pending");
const doneList = document.getElementById("todo-done");

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 204) return null;
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed");
  }
  return payload;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderList(container, items, done) {
  if (!items.length) {
    container.innerHTML = '<li class="todo-empty">No tasks</li>';
    return;
  }

  container.innerHTML = items
    .map((item) => {
      const notes = item.notes
        ? `<p class="todo-item__notes">${escapeHtml(item.notes)}</p>`
        : "";
      return `
        <li class="todo-item" data-id="${item.id}">
          <div>
            <p class="todo-item__title">${escapeHtml(item.title)}</p>
            ${notes}
          </div>
          <div class="todo-item__actions">
            <button type="button" class="btn" data-action="${done ? "undo" : "done"}">${done ? "Undo" : "Done"}</button>
            <button type="button" class="btn btn--danger" data-action="delete">Delete</button>
          </div>
        </li>
      `;
    })
    .join("");
}

async function loadTodos() {
  const items = await request("/api/todo/items");
  const pending = items.filter((item) => !item.is_done);
  const done = items.filter((item) => item.is_done);
  renderList(pendingList, pending, false);
  renderList(doneList, done, true);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = titleInput.value.trim();
  const notes = notesInput.value.trim();
  if (!title) return;
  await request("/api/todo/items", {
    method: "POST",
    body: JSON.stringify({ title, notes: notes || null }),
  });
  form.reset();
  await loadTodos();
});

async function onListClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const itemEl = event.target.closest(".todo-item");
  if (!itemEl) return;
  const itemId = Number(itemEl.dataset.id);
  const action = button.dataset.action;

  if (action === "delete") {
    await request(`/api/todo/items/${itemId}`, { method: "DELETE" });
  } else {
    await request(`/api/todo/items/${itemId}`, {
      method: "PUT",
      body: JSON.stringify({ is_done: action === "done" }),
    });
  }
  await loadTodos();
}

pendingList.addEventListener("click", onListClick);
doneList.addEventListener("click", onListClick);

loadTodos().catch((error) => {
  console.error(error);
  pendingList.innerHTML = '<li class="todo-empty">Failed to load tasks</li>';
  doneList.innerHTML = '<li class="todo-empty">Failed to load tasks</li>';
});
