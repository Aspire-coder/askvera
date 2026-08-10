import { useEffect, useMemo, useRef, useState } from "react";
import { AdminApi, demo, withDemoFallback, type AdminCredentials, type DataMode } from "../api";
import { CheckIcon, FileIcon, RefreshIcon, UploadIcon } from "../icons";
import type { AdminConfig, IngestionJob } from "../types";

const readableType = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const formatSize = (value: number) => value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(value / 1024)} KB`;

export function KnowledgeUploader({ credentials }: { credentials: AdminCredentials }) {
  const [config, setConfig] = useState<AdminConfig>(demo.config);
  const [jobs, setJobs] = useState<IngestionJob[]>(demo.jobs);
  const [mode, setMode] = useState<DataMode>("demo");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [country, setCountry] = useState("BE");
  const [language, setLanguage] = useState("nl");
  const [documentType, setDocumentType] = useState("policy");
  const [accessScope, setAccessScope] = useState("country");
  const [version, setVersion] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [logicalDocumentId, setLogicalDocumentId] = useState("");
  const [documentOwner, setDocumentOwner] = useState("");
  const [approvalReference, setApprovalReference] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | null>(null);

  const refresh = async () => {
    const api = new AdminApi(credentials);
    const [configResult, jobsResult] = await Promise.all([
      withDemoFallback(() => api.config(), demo.config),
      withDemoFallback(() => api.ingestions(), demo.jobs)
    ]);
    setConfig(configResult.data);
    setJobs(jobsResult.data);
    setMode(configResult.mode === "live" && jobsResult.mode === "live" ? "live" : "demo");
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(timer);
  }, [credentials.accessToken, credentials.apiKey]);

  useEffect(() => {
    setAccessScope(documentType === "office_directory" ? "global" : "country");
  }, [documentType]);

  const selectedMarket = config.countries.find((market) => market.code === country) || config.countries[0];
  const languages = selectedMarket?.languages || [];
  useEffect(() => {
    if (!languages.some((option) => option.code === language) && languages[0]) setLanguage(languages[0].code);
  }, [country, config]);

  const acceptedExtensions = useMemo(() => ".pdf,.docx,.txt,.md,.csv,.html,.htm", []);
  const chooseFile = (candidate?: File) => {
    if (!candidate) return;
    setNotice("");
    if (candidate.size > config.maxUploadBytes) {
      setNotice(`That file is larger than ${formatSize(config.maxUploadBytes)}.`);
      return;
    }
    const extension = candidate.name.slice(candidate.name.lastIndexOf(".")).toLowerCase();
    if (!acceptedExtensions.split(",").includes(extension)) {
      setNotice("That file type is not supported. Choose PDF, DOCX, text, Markdown, CSV or HTML.");
      return;
    }
    setFile(candidate);
  };

  const upload = async () => {
    if (!file || (!credentials.accessToken && !credentials.apiKey)) {
      setNotice(!credentials.accessToken && !credentials.apiKey ? "Sign in before uploading." : "Choose a document first.");
      return;
    }
    const formData = new FormData();
    formData.set("file", file);
    formData.set("country", country);
    formData.set("language", language);
    formData.set("document_type", documentType);
    formData.set("access_scope", accessScope);
    formData.set("document_version", version);
    formData.set("effective_date", effectiveDate);
    formData.set("logical_document_id", logicalDocumentId);
    formData.set("document_owner", documentOwner);
    formData.set("approval_reference", approvalReference);
    setSubmitting(true);
    setNotice("");
    uploadController.current = new AbortController();
    try {
      const result = await new AdminApi(credentials).upload(formData, uploadController.current.signal);
      setNotice(`${result.filename} was verified and queued for extraction and indexing.`);
      setFile(null);
      await refresh();
    } catch (error) {
      setNotice(error instanceof DOMException && error.name === "AbortError" ? "Upload cancelled before processing began." : error instanceof Error ? error.message : "Upload failed. The document was not queued.");
    } finally {
      uploadController.current = null;
      setSubmitting(false);
    }
  };

  const cancelUpload = () => uploadController.current?.abort();

  return (
    <section className="page-section" aria-labelledby="knowledge-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Knowledge operations</span>
          <h1 id="knowledge-title">Add knowledge. Keep control.</h1>
          <p>Upload approved content, describe it once, and follow it into the search index.</p>
        </div>
        <span className={`mode-pill ${mode}`}><span />{mode === "live" ? "Connected" : "Demo data"}</span>
      </div>

      <div className="uploader-layout">
        <div className="upload-card surface">
          <div
            className={`drop-zone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
            onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files[0]); }}
          >
            <input ref={inputRef} type="file" accept={acceptedExtensions} onChange={(event) => chooseFile(event.target.files?.[0])} />
            <div className="drop-icon">{file ? <FileIcon /> : <UploadIcon />}</div>
            {file ? (
              <><strong>{file.name}</strong><span>{formatSize(file.size)} · Ready to describe</span><button className="text-button" onClick={() => inputRef.current?.click()}>Choose another</button></>
            ) : (
              <><strong>Drop an approved document here</strong><span>PDF, Word, text, Markdown, CSV or HTML · Up to {formatSize(config.maxUploadBytes)}</span><button className="button secondary" onClick={() => inputRef.current?.click()}>Choose file</button></>
            )}
          </div>

          <div className="metadata-form">
            <div className="form-field span-2"><label>Content type</label><div className="type-options">
              {config.documentTypes.map((type) => <button key={type} type="button" className={documentType === type ? "selected" : ""} onClick={() => setDocumentType(type)}>{readableType(type)}</button>)}
            </div></div>
            <div className="form-field"><label htmlFor="market">Market</label><select id="market" value={country} onChange={(event) => setCountry(event.target.value)}>{config.countries.map((market) => <option key={market.code} value={market.code}>{market.name}</option>)}</select></div>
            <div className="form-field"><label htmlFor="language">Language</label><select id="language" value={language} onChange={(event) => setLanguage(event.target.value)}>{languages.map((option) => <option key={option.code} value={option.code}>{option.name}</option>)}</select></div>
            <div className="form-field"><label htmlFor="scope">Availability</label><select id="scope" value={accessScope} onChange={(event) => setAccessScope(event.target.value)}><option value="country">Selected market only</option><option value="global">All markets</option></select></div>
            <div className="form-field"><label htmlFor="version">Document version</label><input id="version" value={version} onChange={(event) => setVersion(event.target.value)} placeholder="e.g. 2026.3" /></div>
            <div className="form-field"><label htmlFor="effective">Effective date</label><input id="effective" type="date" value={effectiveDate} onChange={(event) => setEffectiveDate(event.target.value)} /></div>
            <div className="form-field"><label htmlFor="logical-document">Stable document ID</label><input id="logical-document" value={logicalDocumentId} onChange={(event) => setLogicalDocumentId(event.target.value)} placeholder="e.g. US-company-policy" /></div>
            <div className="form-field"><label htmlFor="owner">Document owner</label><input id="owner" value={documentOwner} onChange={(event) => setDocumentOwner(event.target.value)} placeholder="Policy or compliance owner" /></div>
            <div className="form-field"><label htmlFor="approval">Approval reference</label><input id="approval" value={approvalReference} onChange={(event) => setApprovalReference(event.target.value)} placeholder="Ticket, memo or approval ID" /></div>
            <div className="form-field upload-action"><span className="helper">Files are checked before queueing. If the connection stops, the job is not activated until processing completes.</span>{submitting ? <button className="button secondary" onClick={cancelUpload}>Cancel upload</button> : <button className="button primary" disabled={!file} onClick={() => void upload()}>Upload and index</button>}</div>
          </div>
          {notice ? <div className="notice" role="status">{notice}</div> : null}
        </div>

        <aside className="processing-card surface">
          <span className="eyebrow">What happens next</span>
          <ol className="processing-steps">
            <li><span>1</span><div><strong>Secure upload</strong><p>Original content is stored with market and version metadata.</p></div></li>
            <li><span>2</span><div><strong>Intelligent extraction</strong><p>Pages, headings, tables and readable blocks become focused chunks.</p></div></li>
            <li><span>3</span><div><strong>Semantic indexing</strong><p>Each chunk receives an embedding and searchable metadata.</p></div></li>
            <li><span>4</span><div><strong>Atomic activation</strong><p>The previous source is replaced only when the new index is complete.</p></div></li>
          </ol>
          <div className="supported-note"><CheckIcon /><span>Limited to approved company policies and the global office directory.</span></div>
        </aside>
      </div>

      <div className="jobs-section">
        <div className="section-heading"><div><h2>Document activity</h2><p>Recent ingestion jobs and indexing progress.</p></div><button className="button secondary" onClick={() => void refresh()}><RefreshIcon /> Refresh</button></div>
        <div className="jobs-table surface">
          <div className="table-row table-head"><span>Document</span><span>Market</span><span>Type</span><span>Status</span><span>Chunks</span></div>
          {jobs.map((job) => <div className="table-row" key={job.job_id}>
            <span className="document-cell"><FileIcon /><span><strong>{job.filename}</strong><small>{job.document_version || "No version"}</small></span></span>
            <span>{job.access_scope === "global" ? "Global" : `${job.country} · ${job.language.toUpperCase()}`}</span>
            <span>{readableType(job.document_type)}</span>
            <span><span className={`status-label ${job.status}`}>{job.status}</span>{job.status !== "ready" && job.status !== "failed" ? <span className="mini-progress"><i style={{ width: `${job.progress}%` }} /></span> : null}</span>
            <span>{job.section_count || "—"}</span>
          </div>)}
        </div>
      </div>
    </section>
  );
}
