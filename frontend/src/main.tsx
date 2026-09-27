import React, { useState } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import BodyWorkspace from './BodyWorkspace'
import './styles.css'
import './components/body.css'

function Root() {
  const [body, setBody] = useState(false)
  if (body) return <BodyWorkspace onBack={() => setBody(false)} />
  return <div className="rootWithStage4"><App/><button className="stage4Launch" type="button" onClick={() => setBody(true)}>Corpo · Etapa 4</button></div>
}

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><Root/></React.StrictMode>)
