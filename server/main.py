*** Begin Patch
*** Update File: server/main.py
@@
-from .clone_and_index import clone_and_index_repo
-from .llm_provider import GeminiClient
+from .clone_and_index import clone_and_index_repo
+from .llm_provider import GeminiClient
+from .docgen_api import generate_docs_for_job
+from .cr_engine import propose_cr, apply_patch
@@
 def _run_index(job_id: str, repo_url: str, branch: str | None, token: str | None):
     try:
         jobs[job_id]["status"] = "cloning"
         _append_log(job_id, f"Cloning {repo_url} ...")
         dest = clone_and_index_repo(repo_url, branch, token, job_id, work_root=WORK_DIR)
-        jobs[job_id]["status"] = "parsing"
-        _append_log(job_id, f"Index created at {dest}")
-        jobs[job_id]["status"] = "done"
+        jobs[job_id]["status"] = "parsing"
+        _append_log(job_id, f"Index created at {dest}")
+
+        # generate docs automatically after indexing
+        try:
+            jobs[job_id]["status"] = "docgen"
+            _append_log(job_id, "Generating SRS/TDD and diagrams...")
+            job_root = WORK_DIR / job_id
+            docs_dir = generate_docs_for_job(job_root)
+            _append_log(job_id, f"Docs generated at {docs_dir}")
+        except Exception as e:
+            _append_log(job_id, f"Docgen failed: {e}")
+
+        jobs[job_id]["status"] = "done"
*** End Patch
