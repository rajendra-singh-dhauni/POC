import React, {useState} from 'react';
import axios from 'axios';

function App(){
  const [repoUrl, setRepoUrl] = useState('');
  const [jobId, setJobId] = useState(null);
  const [logs, setLogs] = useState([]);

  const [crText, setCrText] = useState('');
  const [impact, setImpact] = useState(null);
  const [patchPreview, setPatchPreview] = useState(null);

  const submit = async () => {
    const resp = await axios.post('/api/submit-repo', { repo_url: repoUrl });
    setJobId(resp.data.job_id);
  }

  const pollStatus = async () => {
    if(!jobId) return;
    const resp = await axios.get(`/api/job-status/${jobId}`);
    setLogs(resp.data.logs || []);
  }

  const proposeCR = async () => {
    if(!jobId || !crText) return;
    const resp = await axios.post('/api/propose-cr', { job_id: jobId, cr_text: crText });
    setImpact(resp.data.impact);
    setPatchPreview(resp.data.patch);
  }

  const applyCR = async (mode='dry') => {
    if(!jobId) return;
    const resp = await axios.post('/api/apply-cr', { job_id: jobId, patch: patchPreview, mode });
    alert(JSON.stringify(resp.data));
  }

  return (
    <div style={{padding:20}}>
      <h1>CGR Lite - Upload GitHub Repo</h1>
      <input style={{width:'80%'}} value={repoUrl} onChange={e=>setRepoUrl(e.target.value)} placeholder="https://github.com/owner/repo.git" />
      <button onClick={submit}>Submit</button>
      {jobId && <div>
        <h3>Job: {jobId}</h3>
        <button onClick={pollStatus}>Refresh Status</button>
        <pre>{logs.join('\n')}</pre>

        <hr />
        <h3>Propose Change Request (CR)</h3>
        <textarea rows={4} style={{width:'80%'}} value={crText} onChange={e=>setCrText(e.target.value)} placeholder="Describe the change you want to make..." />
        <br />
        <button onClick={proposeCR}>Propose CR</button>

        {impact && <div style={{marginTop:10}}>
          <h4>Impact</h4>
          <pre>{JSON.stringify(impact, null, 2)}</pre>
        </div>}

        {patchPreview && <div style={{marginTop:10}}>
          <h4>Patch Preview</h4>
          <pre style={{whiteSpace:'pre-wrap'}}>{patchPreview}</pre>
          <button onClick={()=>applyCR('dry')}>Apply (dry-run)</button>
          <button onClick={()=>applyCR('apply')}>Apply (apply)</button>
        </div>}

      </div>}
    </div>
  )
}

export default App;
