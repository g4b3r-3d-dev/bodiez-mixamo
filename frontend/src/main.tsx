import React,{useState} from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import BodyWorkspace from './BodyWorkspace'
import AnimationWorkspace from './AnimationWorkspace'
import Stage6Workspace from './Stage6Workspace'
import './styles.css'
import './components/body.css'
import './components/animation.css'
import './components/stage6.css'

type Workspace='main'|'body'|'animation'|'experience'

function Root(){
  const [workspace,setWorkspace]=useState<Workspace>('main')
  if(workspace==='body')return <BodyWorkspace onBack={()=>setWorkspace('main')}/>
  if(workspace==='animation')return <AnimationWorkspace onBack={()=>setWorkspace('main')}/>
  if(workspace==='experience')return <Stage6Workspace onBack={()=>setWorkspace('main')}/>
  return <div className="rootWithStages"><App/><button className="stage6Launch" type="button" onClick={()=>setWorkspace('experience')}>Experiência · Etapa 6</button><button className="stage5Launch" type="button" onClick={()=>setWorkspace('animation')}>Poses/Animações · Etapa 5</button><button className="stage4Launch" type="button" onClick={()=>setWorkspace('body')}>Corpo · Etapa 4</button></div>
}

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><Root/></React.StrictMode>)
