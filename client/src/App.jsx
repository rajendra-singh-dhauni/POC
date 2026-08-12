import React, {useState} from 'react';
import axios from 'axios';

function App(){
  const [repoUrl, setRepoUrl] = useState('');
  const [jobId, setJobId] = useState(null);
  const [logs, setLogs] = useState([]);

  const submit = async () => {
    const resp = await axios.post('/api/submit-repo', { repo_url: repoUrl });
    setJobId(resp.data.job_id);
  }

  const pollStatus = async () => {
    if(!jobId) return;
    const resp = await axios.get(`/api/job-status/${jobId}`);
    setLogs(resp.data.logs || []);
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
      </div>}
    </div>
  )
}

export default App;
