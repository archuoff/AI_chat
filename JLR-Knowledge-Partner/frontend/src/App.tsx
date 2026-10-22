import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { UsersView } from './admin/UsersView'
import { ChatView } from './chat/ChatView'
import { LoginView } from './components/LoginView'
import { Sidebar, type View } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { api } from './lib/api'
import { auth, type AuthUser } from './lib/auth'
import { storage, uid } from './lib/storage'
import type { DocumentInfo, Session } from './lib/types'
import { ManageView } from './manage/ManageView'

export default function App() {
  const session = useSyncExternalStore(auth.subscribe, auth.get)
  if (!session) return <LoginView />
  // keyed by user: signing in as someone else starts from a clean workspace
  return <Workspace key={session.user.id} user={session.user} />
}

const TITLES: Record<View, { title: string; subtitle?: string }> = {
  chat: { title: 'New conversation', subtitle: undefined },
  manage: { title: 'Manage knowledge', subtitle: 'Add documents, check what the assistant learned, and fix anything that looks off' },
  users: { title: 'Users & usage', subtitle: 'Create accounts, set roles and domain access, and follow question and token usage' },
}

function Workspace({ user }: { user: AuthUser }) {
  const isDev = user.role === 'developer'
  const [view, setView] = useState<View>('chat')
  const [sessions, setSessions] = useState<Session[]>(() => storage.sessions())
  const [activeId, setActiveId] = useState<string>(() => storage.sessions()[0]?.id ?? uid())
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => storage.pref('sidebarCollapsed', false))
  // remembered on wide screens only; on narrow screens the panel is an overlay and starts closed
  const [sourcesOpen, setSourcesOpen] = useState(() => window.matchMedia('(min-width: 1280px)').matches && storage.pref('sourcesOpen', true))

  const refresh = useCallback(async () => {
    await Promise.all([
      isDev ? api.documents().then(setDocs).catch(() => setDocs([])) : Promise.resolve(),
    ])
  }, [isDev])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => storage.setPref('sidebarCollapsed', collapsed), [collapsed])
  useEffect(() => {
    if (window.matchMedia('(min-width: 1280px)').matches) storage.setPref('sourcesOpen', sourcesOpen)
  }, [sourcesOpen])
  useEffect(() => storage.saveSessions(sessions), [sessions])

  const touch = useCallback((id: string, question: string) => {
    setSessions((cur) => {
      const existing = cur.find((s) => s.id === id)
      const title = existing?.title ?? (question.length > 60 ? `${question.slice(0, 57)}…` : question)
      return [{ id, title, updatedAt: Date.now() }, ...cur.filter((s) => s.id !== id)]
    })
  }, [])

  const newChat = () => {
    setActiveId(uid())
    setView('chat')
    setMenuOpen(false)
  }

  const removeSession = (id: string) => {
    api.deleteSession(id).catch(() => {})
    storage.removeMessages(id)
    setSessions((cur) => cur.filter((s) => s.id !== id))
    if (id === activeId) setActiveId(uid())
  }

  const current: View = !isDev && view !== 'chat' ? 'chat' : view
  const title = current === 'chat' ? sessions.find((s) => s.id === activeId)?.title ?? TITLES.chat.title : TITLES[current].title

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar
        user={user}
        view={current}
        onView={(v) => {
          setView(v)
          setMenuOpen(false)
        }}
        sessions={sessions}
        activeId={activeId}
        onSelect={(id) => {
          setActiveId(id)
          setView('chat')
          setMenuOpen(false)
        }}
        onNew={newChat}
        onDelete={removeSession}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed((c) => !c)}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <TopBar
          title={title}
          subtitle={TITLES[current].subtitle}
          onMenu={() => setMenuOpen(true)}
          onToggleSources={current === 'chat' ? () => setSourcesOpen((o) => !o) : undefined}
          sourcesOpen={sourcesOpen}
        />
        {current === 'chat' && (
          <ChatView sessionId={activeId} onTouched={touch} sourcesOpen={sourcesOpen} onSourcesOpen={setSourcesOpen} />
        )}
        {current === 'manage' && <ManageView docs={docs} onRefresh={refresh} />}
        {current === 'users' && <UsersView />}
      </main>
    </div>
  )
}
