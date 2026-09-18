import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'

import { SpinnerIcon } from '@/components/Icons'
import { PageHeader } from '@/components/PageHeader'
import { api } from '@/lib/api'

export function AdminPage() {
  const { t, i18n } = useTranslation()

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: api.admin.users,
  })

  const dateFormat = new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' })

  return (
    <div className="mx-auto h-full max-w-4xl overflow-y-auto px-6 py-8">
      <PageHeader title={t('admin.title')} subtitle={t('admin.subtitle')} />

      {isLoading ? (
        <div className="flex justify-center py-16 text-ink-2">
          <SpinnerIcon />
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-paper-3 text-xs uppercase tracking-wide text-ink-2">
              <tr>
                <th className="px-4 py-3 text-start font-semibold">{t('admin.name')}</th>
                <th className="px-4 py-3 text-start font-semibold">{t('admin.email')}</th>
                <th className="px-4 py-3 text-start font-semibold">{t('admin.role')}</th>
                <th className="px-4 py-3 text-start font-semibold">{t('admin.joined')}</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="border-t border-line">
                  <td className="px-4 py-3 font-medium">{user.display_name}</td>
                  <td className="px-4 py-3 text-ink-2" dir="ltr">
                    {user.email}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                        user.is_admin
                          ? 'bg-primary-50 text-primary'
                          : 'bg-paper-3 text-ink-2'
                      }`}
                    >
                      {user.is_admin ? t('admin.roleAdmin') : t('admin.roleMember')}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-ink-2">
                    {dateFormat.format(new Date(user.created_at))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
