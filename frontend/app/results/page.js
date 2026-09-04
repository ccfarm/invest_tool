import ResultsClient from './results-client'
export async function generateMetadata({searchParams}){const{q=''}=await searchParams;return{title:q?`「${q}」股东持股查询`:'股东持股查询结果',robots:{index:false,follow:true}}}
export default async function Results({searchParams}){const{q='',page='1'}=await searchParams;return <ResultsClient initialQuery={q} initialPage={Number(page)||1}/>}
