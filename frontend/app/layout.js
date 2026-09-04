import '../src/style.css'
import AppShell from '@/components/AppShell'

export const metadata = {
  metadataBase: new URL(process.env.SITE_URL || 'http://www.cats789.fun'),
  title: { default: '股东查询 - A股十大股东持股记录与变动 | 投资工具箱', template: '%s | 投资工具箱' },
  description: '输入股东姓名或 A 股代码，查询 A 股十大股东持股记录与持仓变动。',
  openGraph: { type: 'website', images: ['/og-image.png'] },
}

export default function RootLayout({ children }) {
  return <html lang="zh-CN" suppressHydrationWarning><body><AppShell>{children}</AppShell></body></html>
}
