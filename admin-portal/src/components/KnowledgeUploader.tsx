import { useEffect, useMemo, useRef, useState } from "react";
import { AdminApi, demo, withDemoFallback, type AdminCredentials, type DataMode } from "../api";
import { demoAllowed } from "../auth";
import { CheckIcon, FileIcon, RefreshIcon, UploadIcon } from "../icons";
import type { AdminConfig, IngestionJob, IngestionPreview, IngestionPreviewTest, KnowledgeGeneration } from "../types";

const readableType = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const formatSize = (value: number) => value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(value / 1024)} KB`;
export function KnowledgeUploader({ credentials }: { credentials: AdminCredentials }) {
  const [config, setConfig] = useState<AdminConfig>(demo.config);
  const [jobs, setJobs] = useState<IngestionJob[]>(demoAllowed ? demo.jobs : []);
  const [mode, setMode] = useState<DataMode>(demoAllowed ? "demo" : "live");
  const [loadError, setLoadError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [country, setCountry] = useState("BE");
  const [coverageSelection, setCoverageSelection] = useState("BE");
  const [language, setLanguage] = useState("nl");
  const [documentType, setDocumentType] = useState("policy");
  const [accessScope, setAccessScope] = useState("country");
  const [version, setVersion] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [logicalDocumentId, setLogicalDocumentId] = useState("");
  const [documentOwner, setDocumentOwner] = useState("");
  const [approvalReference, setApprovalReference] = useState("");
  const [reviewBeforePublish, setReviewBeforePublish] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | null>(null);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [preview, setPreview] = useState<IngestionPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [testQuestion, setTestQuestion] = useState("");
  const [testResult, setTestResult] = useState<IngestionPreviewTest | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [publishLoading, setPublishLoading] = useState(false);
  const [deletingJobId, setDeletingJobId] = useState("");
  const [historyJob, setHistoryJob] = useState<IngestionJob | null>(null);
  const [generations, setGenerations] = useState<KnowledgeGeneration[]>([]);
  const [compareVersions, setCompareVersions] = useState<string[]>([]);
  const [rollbackLoading, setRollbackLoading] = useState("");

  const refresh = async () => {
    const api = new AdminApi(credentials);
    try {
      const [configResult, jobsResult] = await Promise.all([
        withDemoFallback(() => api.config(), demo.config),
        withDemoFallback(() => api.ingestions(), demo.jobs)
      ]);
      setConfig(configResult.data);
      setJobs(jobsResult.data);
      setMode(configResult.mode === "live" && jobsResult.mode === "live" ? "live" : "demo");
      setLoadError("");
    } catch (error) {
      setJobs([]);
      setMode("live");
      setLoadError(error instanceof Error ? error.message : "Live document activity could not be loaded.");
    }
  };

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(timer);
  }, [credentials.accessToken, credentials.apiKey]);

  useEffect(() => {
    setAccessScope(documentType === "office_directory" ? "global" : "country");
  }, [documentType]);

  const selectedMarket = config.countries.find((market) => market.code === coverageSelection);
  const uploadMarket = config.countries.find((market) => market.code === country) || config.countries[0];
  const showingGlobalCoverage = coverageSelection === "GLOBAL";
  const languages = uploadMarket?.languages || [];
  const marketJobs = useMemo(
    () => jobs.filter((job) => showingGlobalCoverage ? job.access_scope === "global" : job.access_scope === "global" || job.country === coverageSelection),
    [coverageSelection, jobs, showingGlobalCoverage],
  );
  const readyDocuments = marketJobs.filter((job) => job.status === "ready").length;
  const inProgressDocuments = marketJobs.filter((job) => !["ready", "failed"].includes(job.status)).length;
  const suggestedDocumentId = `${country.toLowerCase()}-${documentType.replaceAll("_", "-")}`;
  useEffect(() => {
    if (!config.countries.some((market) => market.code === country) && config.countries[0]) setCountry(config.countries[0].code);
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
    formData.set("expiry_date", expiryDate);
    formData.set("logical_document_id", logicalDocumentId);
    formData.set("document_owner", documentOwner);
    formData.set("approval_reference", approvalReference);
    formData.set("review_before_publish", String(reviewBeforePublish));
    setSubmitting(true);
    setNotice("");
    uploadController.current = new AbortController();
    try {
      const result = await new AdminApi(credentials).upload(formData, uploadController.current.signal);
      const detected = result.detectedFormat?.format ? ` Detected as ${readableType(result.detectedFormat.format)}.` : "";
      setNotice(`${result.filename} was verified and queued for extraction and indexing.${detected}${reviewBeforePublish ? " It will stay out of live answers until you publish it." : ""}`);
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

  const reviewableJobs = jobs.filter((job) => job.status === "ready_for_review");
  const loadPreview = async (jobId: string) => {
    setSelectedJobId(jobId);
    setPreview(null);
    setTestResult(null);
    setPreviewError("");
    if (!jobId || mode !== "live") return;
    setPreviewLoading(true);
    try {
      const result = await new AdminApi(credentials).ingestionPreview(jobId, 12);
      setPreview(result);
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "The document review could not be loaded.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const runPreviewTest = async () => {
    if (!selectedJobId || !testQuestion.trim()) return;
    setTestLoading(true);
    try {
      const result = await new AdminApi(credentials).testIngestionPreview(selectedJobId, testQuestion.trim());
      setTestResult(result);
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "The staging test could not be completed.");
    } finally {
      setTestLoading(false);
    }
  };

  const publishReview = async () => {
    if (!selectedJobId || !preview?.can_publish) return;
    setPublishLoading(true);
    try {
      const result = await new AdminApi(credentials).publishIngestion(selectedJobId);
      setNotice(`${result.publishedCount} chunks were published. The document is now available to approved retrieval.`);
      setPreview(null);
      setSelectedJobId("");
      await refresh();
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "The document could not be published.");
    } finally {
      setPublishLoading(false);
    }
  };

  const canDeleteDocuments = config.principal?.role === "super_admin" && mode === "live";
  const openHistory = async (job: IngestionJob) => {
    setHistoryJob(job);
    setGenerations([]);
    setCompareVersions([]);
    try {
      const result = await new AdminApi(credentials).ingestionGenerations(job.job_id);
      setGenerations(result);
      setCompareVersions(result.slice(0, 2).map((item) => item.ingestion_id));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Version history could not be loaded.");
    }
  };
  const rollback = async (target: KnowledgeGeneration) => {
    if (!historyJob || !window.confirm(`Roll back ${historyJob.filename} to version ${target.document_version || target.ingestion_id}?`)) return;
    setRollbackLoading(target.ingestion_id);
    try {
      await new AdminApi(credentials).rollbackIngestion(historyJob.job_id, target.ingestion_id);
      setNotice(`${historyJob.filename} was rolled back to ${target.document_version || target.ingestion_id}.`);
      await openHistory(historyJob);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The rollback could not be completed.");
    } finally {
      setRollbackLoading("");
    }
  };
  const deleteDocument = async (job: IngestionJob) => {
    if (!canDeleteDocuments || deletingJobId) return;
    const scope = job.access_scope === "global" ? "all markets" : `${job.country} · ${job.language.toUpperCase()}`;
    const confirmed = window.confirm(`Delete “${job.filename}” (${job.document_version || "no version"}) from ${scope}?\n\nThis removes it from customer retrieval, the search index, and source storage. This cannot be undone.`);
    if (!confirmed) return;
    setDeletingJobId(job.job_id);
    setNotice("");
    try {
      const result = await new AdminApi(credentials).deleteIngestion(job.job_id);
      setNotice(result.message);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The document could not be deleted.");
    } finally {
      setDeletingJobId("");
    }
  };

  return (
    <section className="page-section" aria-labelledby="knowledge-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Knowledge operations</span>
          <h1 id="knowledge-title">Add knowledge. Keep control.</h1>
          <p>Upload approved content, describe it once, and follow it into the search index.</p>
        </div>
        <span className={`mode-pill ${loadError ? "error" : mode}`}><span />{loadError ? "Connection error" : mode === "live" ? "Connected" : "Demo data"}</span>
      </div>

      <section className="knowledge-market-summary surface" aria-labelledby="knowledge-market-title">
        <div className="knowledge-market-selector">
          <label htmlFor="knowledge-market"><span className="eyebrow">Coverage view</span><strong id="knowledge-market-title">Which documents should we review?</strong></label>
          <select id="knowledge-market" value={coverageSelection} onChange={(event) => setCoverageSelection(event.target.value)} aria-label="Select knowledge coverage">
            <option value="GLOBAL">Global documents (all markets)</option>
            {config.countries.map((market) => <option key={market.code} value={market.code}>{market.name} ({market.code})</option>)}
          </select>
        </div>
        <div className="knowledge-market-stats" aria-label={`${showingGlobalCoverage ? "Global" : selectedMarket?.name || "Selected market"} document summary`}>
          <div><strong>{marketJobs.length}</strong><span>Available here</span></div>
          <div><strong>{readyDocuments}</strong><span>Ready</span></div>
          <div><strong>{inProgressDocuments}</strong><span>In progress</span></div>
        </div>
      </section>

      <section className="knowledge-existing surface" aria-labelledby="existing-documents-title">
        <div className="section-heading"><div><span className="eyebrow">Current coverage</span><h2 id="existing-documents-title">{showingGlobalCoverage ? "Global documents" : `Documents available for ${selectedMarket?.name || "this market"}`}</h2><p>{showingGlobalCoverage ? "Documents available to every market, including global directories and FAQs." : "Global documents are included. Use names and versions to avoid replacing the wrong document."}</p></div><span className="review-safety">{marketJobs.length} found</span></div>
        {loadError ? <div className="review-empty" role="alert">{loadError} Existing documents are hidden until live data is available.</div> : marketJobs.filter((job) => job.status !== "deleted").length ? <div className="knowledge-existing-list">{marketJobs.filter((job) => job.status !== "deleted").map((job) => <article className="knowledge-existing-row" key={job.job_id}><FileIcon /><div><strong>{job.filename}</strong><small>{job.access_scope === "global" ? "Global · available to all markets" : `${job.language.toUpperCase()} · ${job.country}`} · {readableType(job.document_type)} · {job.document_version || "No version"}{job.expiry_date ? ` · expires ${new Date(`${job.expiry_date}T00:00:00`).toLocaleDateString()}` : ""}</small><small>{job.malware_scan_status === "clean" ? "Malware scan passed" : job.malware_scan_status === "blocked" ? "Blocked by malware scan" : job.malware_scan_status === "pending" ? "Malware scan pending" : "Preflight complete"} · {job.status === "ready" ? "Indexed in OpenSearch" : "Not active in retrieval"}</small></div><span className={`status-label ${job.status}`}>{job.status}</span><span className="knowledge-chunks">{job.section_count || 0} chunks</span><button className="button secondary small" onClick={() => void openHistory(job)}>Versions</button>{canDeleteDocuments ? <button className="button danger small" disabled={deletingJobId === job.job_id} onClick={() => void deleteDocument(job)}>{deletingJobId === job.job_id ? "Deleting..." : "Delete"}</button> : null}</article>)}</div> : <div className="review-empty">No documents are currently available for this coverage.</div>}
      </section>

      {historyJob ? <section className="knowledge-history surface"><div className="section-heading"><div><span className="eyebrow">Version control</span><h2>{historyJob.filename}</h2><p>Compare retained generations and restore a previously verified version.</p></div><button className="button secondary" onClick={() => setHistoryJob(null)}>Close</button></div>{generations.length ? <><div className="version-compare-select"><label>Compare versions<select value={compareVersions[0] || ""} onChange={(event) => setCompareVersions([event.target.value, compareVersions[1] || ""])}>{generations.map((item) => <option key={item.ingestion_id} value={item.ingestion_id}>{item.document_version || item.ingestion_id}</option>)}</select></label><label>With<select value={compareVersions[1] || ""} onChange={(event) => setCompareVersions([compareVersions[0] || "", event.target.value])}>{generations.map((item) => <option key={item.ingestion_id} value={item.ingestion_id}>{item.document_version || item.ingestion_id}</option>)}</select></label></div><div className="version-comparison">{compareVersions.map((id) => generations.find((item) => item.ingestion_id === id)).filter(Boolean).map((item) => <article key={item!.ingestion_id}><strong>{item!.document_version || "Unversioned"}</strong><span className={`status-label ${item!.status}`}>{item!.status}</span><dl><div><dt>Chunks</dt><dd>{item!.section_count}</dd></div><div><dt>Effective</dt><dd>{item!.effective_date || "Not set"}</dd></div><div><dt>Expiry</dt><dd>{item!.expiry_date || "Not set"}</dd></div><div><dt>Malware</dt><dd>{item!.malware_scan_status}</dd></div><div><dt>Activated</dt><dd>{item!.activated_at ? new Date(item!.activated_at).toLocaleString() : "Not activated"}</dd></div></dl>{canDeleteDocuments && item!.status !== "active" ? <button className="button secondary" disabled={rollbackLoading === item!.ingestion_id} onClick={() => void rollback(item!)}>{rollbackLoading === item!.ingestion_id ? "Rolling back..." : "Restore this version"}</button> : null}</article>)}</div></> : <div className="empty-state">No retained version history is available for this document.</div>}</section> : null}

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
            <div className="form-field"><label htmlFor="market">Market</label><select id="market" value={country} onChange={(event) => setCountry(event.target.value)}>{config.countries.map((market) => <option key={market.code} value={market.code}>{market.name} ({market.code})</option>)}</select></div>
            <div className="form-field"><label htmlFor="language">Language</label><select id="language" value={language} onChange={(event) => setLanguage(event.target.value)}>{languages.map((option) => <option key={option.code} value={option.code}>{option.name}</option>)}</select></div>
            <div className="form-field"><label htmlFor="scope">Availability</label><select id="scope" value={accessScope} onChange={(event) => setAccessScope(event.target.value)}><option value="country">Selected market only</option><option value="global">All markets</option></select></div>
            <div className="form-field"><label htmlFor="version">Document version</label><input id="version" value={version} onChange={(event) => setVersion(event.target.value)} placeholder="e.g. 2026.3" /></div>
            <div className="form-field"><label htmlFor="effective">Effective date</label><input id="effective" type="date" value={effectiveDate} onChange={(event) => setEffectiveDate(event.target.value)} /></div>
            <div className="form-field"><label htmlFor="expiry">Review or expiry date</label><input id="expiry" type="date" value={expiryDate} onChange={(event) => setExpiryDate(event.target.value)} /><small className="field-help">The portal will flag documents approaching this date.</small></div>
            <div className="form-field"><label htmlFor="logical-document">Stable document ID</label><input id="logical-document" value={logicalDocumentId} onChange={(event) => setLogicalDocumentId(event.target.value)} placeholder={suggestedDocumentId} /><small className="field-help">Suggested: {suggestedDocumentId}. Keep this stable when replacing the same document.</small></div>
            <div className="form-field"><label htmlFor="owner">Document owner</label><input id="owner" value={documentOwner} onChange={(event) => setDocumentOwner(event.target.value)} placeholder="Policy or compliance owner" /></div>
            <div className="form-field"><label htmlFor="approval">Approval reference</label><input id="approval" value={approvalReference} onChange={(event) => setApprovalReference(event.target.value)} placeholder="Ticket, memo or approval ID" /></div>
            <label className="review-toggle"><input type="checkbox" checked={reviewBeforePublish} onChange={(event) => setReviewBeforePublish(event.target.checked)} /><span><strong>Review chunks before publishing</strong><small>Keep this document out of live answers until you test and approve it.</small></span></label>
            <div className="form-field upload-action"><span className="helper">Files are checked before queueing. If the connection stops, the job is not activated until processing completes.</span>{submitting ? <button className="button secondary" onClick={cancelUpload}>Cancel upload</button> : <button className="button primary" disabled={!file} onClick={() => void upload()}>{reviewBeforePublish ? "Upload for review" : "Upload and index"}</button>}</div>
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

      <section className="review-panel surface" aria-labelledby="review-title">
        <div className="section-heading"><div><span className="eyebrow">Staging workspace</span><h2 id="review-title">Review before publish</h2><p>Check the extracted chunks and try a question before a document can affect customer answers.</p></div><span className="review-safety">Staging only</span></div>
        {loadError ? <div className="review-empty" role="alert">{loadError} Refresh after the live service is available. No demo documents are shown in production.</div> : mode !== "live" ? <div className="review-empty">Connect the portal to load staging documents. Demo data never publishes anything.</div> : <>
          <div className="review-toolbar"><label htmlFor="review-job">Document ready for review</label><select id="review-job" value={selectedJobId} onChange={(event) => void loadPreview(event.target.value)}><option value="">Select a reviewed document</option>{reviewableJobs.map((job) => <option key={job.job_id} value={job.job_id}>{job.filename} ({job.section_count} chunks)</option>)}</select><button className="button secondary" disabled={!selectedJobId || previewLoading} onClick={() => void loadPreview(selectedJobId)}><RefreshIcon /> Check document</button></div>
          {previewLoading ? <div className="review-empty">Loading the extracted chunks...</div> : null}
          {previewError ? <div className="notice error" role="alert">{previewError}</div> : null}
          {preview ? <>
            <div className="review-summary"><div className="review-stat"><strong>{preview.summary.chunk_count}</strong><span>chunks</span></div><div className="review-stat"><strong>{preview.summary.page_count}</strong><span>pages found</span></div><div className="review-stat"><strong>{preview.summary.average_chars}</strong><span>average characters</span></div><div className="review-stat"><strong>{preview.summary.largest_chars}</strong><span>largest chunk</span></div></div>
            {preview.summary.warnings.length ? <div className="review-warnings"><strong>Review notes</strong>{preview.summary.warnings.map((warning) => <span key={warning}>{warning}</span>)}</div> : <div className="review-good"><CheckIcon /> No chunk quality warnings in this document.</div>}
            <div className="review-chunk-list">{preview.chunks.map((chunk) => <article className="review-chunk" key={chunk.id}><div className="review-chunk-meta"><strong>{chunk.sectionId || "Content block"}</strong><span>{chunk.title || "Untitled"}</span><span>{chunk.page ? `Page ${chunk.page}${chunk.endPage && chunk.endPage !== chunk.page ? `-${chunk.endPage}` : ""}` : "Page not detected"}</span></div><div className="review-chunk-content">{chunk.content || "No readable text found."}</div></article>)}</div>
            <div className="review-test"><div><strong>Test a question against this document</strong><span>Searches only this staged document.</span></div><div className="review-test-row"><input value={testQuestion} onChange={(event) => setTestQuestion(event.target.value)} placeholder="e.g. What are the qualification requirements?" onKeyDown={(event) => { if (event.key === "Enter") void runPreviewTest(); }} /><button className="button secondary" disabled={testLoading || !testQuestion.trim()} onClick={() => void runPreviewTest()}>{testLoading ? "Testing..." : "Test question"}</button></div>{testResult ? <div className="review-results"><strong>{testResult.matchCount} matching chunks</strong>{testResult.matches.map((match) => <div className="review-result" key={`${match.sectionId}-${match.page}`}><b>{match.title || match.sectionId}</b><span>Page {match.page || "-"} · score {Number(match.score || 0).toFixed(2)}</span><p>{match.excerpt}</p></div>)}</div> : null}</div>
            <div className="review-publish"><span>{preview.can_publish ? "The full staged document is ready." : "The document is not complete enough to publish."}</span><button className="button primary" disabled={!preview.can_publish || publishLoading} onClick={() => void publishReview()}>{publishLoading ? "Publishing..." : "Publish approved document"}</button></div>
          </> : <div className="review-empty">{reviewableJobs.length ? "Select a document to inspect its chunks." : "Upload a document with review enabled to see it here."}</div>}
        </>}
      </section>

      <div className="jobs-section">
        <div className="section-heading"><div><h2>Document activity</h2><p>Recent ingestion jobs and indexing progress.</p></div><button className="button secondary" onClick={() => void refresh()}><RefreshIcon /> Refresh</button></div>
        <div className="jobs-table surface">
          <div className="table-row table-head"><span>Document</span><span>Market</span><span>Type</span><span>Status</span><span>Chunks</span><span>Actions</span></div>
          {marketJobs.length ? marketJobs.map((job) => <div className="table-row" key={job.job_id}>
            <span className="document-cell"><FileIcon /><span><strong>{job.filename}</strong><small>{job.document_version || "No version"}</small></span></span>
            <span>{job.access_scope === "global" ? "Global" : `${job.country} · ${job.language.toUpperCase()}`}</span>
            <span>{readableType(job.document_type)}</span>
            <span><span className={`status-label ${job.status}`}>{job.status}</span>{job.status !== "ready" && job.status !== "failed" ? <span className="mini-progress"><i style={{ width: `${job.progress}%` }} /></span> : null}{job.status === "failed" && job.error_message ? <small className="job-error">{job.error_message}</small> : null}</span>
            <span>{job.section_count || "—"}</span>
            <span>{canDeleteDocuments && job.status !== "deleted" ? <button className="button danger small" disabled={deletingJobId === job.job_id} onClick={() => void deleteDocument(job)}>{deletingJobId === job.job_id ? "Deleting..." : "Delete"}</button> : job.status === "deleted" ? "Deleted" : ""}</span>
          </div>) : <div className="empty-state">{loadError || "No document activity found."}</div>}
        </div>
      </div>
    </section>
  );
}
