import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';

async function request(method, id, body) {
  const suffix = id === undefined ? '' : `/${id}`;
  const response = await fetch(`api/items${suffix}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(typeof error?.detail === 'string' ? error.detail : `Request failed (${response.status}).`);
  }
  if (response.status !== 204) return response.json();
}

function Tracker({ title, itemLabel }) {
  const [items, setItems] = useState([]);
  const [input, setInput] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    request('GET').then(setItems).catch(error => setError(error.message)).finally(() => setLoading(false));
  }, []);

  async function mutate(operation) {
    if (busy || loading) return;
    setBusy(true);
    setError('');
    try {
      await operation();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }

  function add(event) {
    event.preventDefault();
    const title = input.trim();
    if (!title || title.length > 80) {
      setError('Enter an item title between 1 and 80 characters.');
      return;
    }
    return mutate(async () => {
      const created = await request('POST', undefined, { title });
      setItems(previous => [...previous, created]);
      setInput('');
    });
  }

  function changeInput(eventOrText) {
    const value = typeof eventOrText === 'string' ? eventOrText : eventOrText?.target?.value;
    if (typeof value === 'string') setInput(value);
  }

  function toggle(item) {
    return mutate(async () => {
      const updated = await request('PATCH', item.id, { done: !item.done });
      setItems(previous => previous.map(row => row.id === updated.id ? updated : row));
    });
  }

  function remove(id) {
    return mutate(async () => {
      await request('DELETE', id);
      setItems(previous => previous.filter(row => row.id !== id));
    });
  }

  return <App title={title} itemLabel={itemLabel} items={items} input={input} onInput={changeInput}
    onAdd={add} onToggle={toggle} onDelete={remove} error={error} busy={busy || loading} loading={loading} />;
}

const root = document.getElementById('root');
createRoot(root).render(<Tracker title={root.dataset.title} itemLabel={root.dataset.itemLabel} />);
