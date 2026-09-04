import SearchBox from '@/components/SearchBox'
export default function Home(){return <><h1 className="sr-only">股东持股查询</h1><SearchBox/><section className="empty-state"><div className="empty-icon">🔍</div><p>在上方输入股东姓名或 A 股代码，即可查看相关持股信息与分析结果。</p></section></>}
