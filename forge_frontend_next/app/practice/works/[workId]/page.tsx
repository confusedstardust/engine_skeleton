"use client";
import Link from "next/link";
import {useParams} from "next/navigation";
import {useEffect,useState} from "react";
import {forgeApi} from "../../../../lib/api-client";
import {workApi} from "../../../../lib/work-api";
import {withBasePath} from "../../../base-path";
import {supportsGestureBridge} from "../../../../lib/gesture-bridge/capability";
import GestureWorkHost from "../../../../components/gesture/gesture-work-host";
import styles from "./public-work.module.css";

type PlayerWork={id:string;title:string;summary?:string;kind:string;subject?:string|null;grade?:string|null;tags?:string[];version:number};
type Player={work:PlayerWork;src:string;html:string;isPrivate:boolean;versionId?:string};
/** Public links show the published snapshot; private fallback is always owner-scoped. */
export default function PublicWorkPage(){
  const {workId}=useParams<{workId:string}>();
  const [player,setPlayer]=useState<Player|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  useEffect(()=>{
    if(!/^[0-9a-f]{32}$/.test(workId||"")){setError("作品链接无效");setLoading(false);return;}
    let active=true;setLoading(true);setError("");setPlayer(null);
    async function privateWork(){
      const {work}=await workApi.get(workId);
      const version=work.versions.find(v=>v.id===work.current_version_id);
      if(!version)throw Error("No saved version");
      const html=await (await workApi.html(workId,version.id)).text();
      if(!active)return;
      setPlayer({
        isPrivate:true,html,versionId:version.id,
        src:withBasePath(`/api/forge/works/${workId}/assets/${version.id}/index.html`),
        work:{id:work.id,title:work.title,summary:work.summary,kind:work.kind,
          subject:work.subject,grade:work.grade,tags:work.tags,version:version.version_number}
      });
    }
    async function load(){
      const ownerView=new URLSearchParams(window.location.search).get("owner")==="1";
      try{
        if(ownerView)await privateWork();
        else{
          try{
            const info=await forgeApi<PlayerWork>(`/public/works/${workId}`);
            const html=await (await forgeApi.response(`/public/works/${workId}/index.html`)).text();
            if(active)setPlayer({isPrivate:false,work:info,html,
              src:withBasePath(`/api/forge/public/works/${workId}/index.html`)});
          }catch{await privateWork();}
        }
      }catch{if(active)setError("作品未发布、已撤回，或暂时无法访问");}
      finally{if(active)setLoading(false);}
    }
    void load();return()=>{active=false;};
  },[workId]);
  return <main className={styles.page}>
    {player?.isPrivate&&<Link className={styles.back} href="/history">我的作品</Link>}
    {loading&&<p className={styles.message}>正在读取互动学习作品…</p>}
    {error&&!loading&&<p role="alert" className={styles.message}>{error}</p>}
    {player&&!loading&&<section className={styles.content}>
      <div className={styles.title}>
        <h1>{player.work.title}</h1>
        <p>{[player.work.subject,player.work.grade,`V${player.work.version}`].filter(Boolean).join(" · ")}</p>
        {player.work.summary&&<p>{player.work.summary}</p>}
      </div>
      <div className={styles.viewer}>
        {supportsGestureBridge(player.html)
          ? <GestureWorkHost key={player.work.id+":"+player.versionId+":"+player.work.version}
              html={player.html} label={player.work.title} fullHeight/>
          : <iframe key={player.src} title={player.work.title} sandbox="allow-scripts"
              allow="fullscreen" allowFullScreen referrerPolicy="no-referrer" src={player.src}/>}
      </div>
    </section>}
  </main>;
}
