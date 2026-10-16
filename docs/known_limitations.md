# Known Limitations and Missing Data

Last updated 2026-10-16.

## 1. No source has been retrieved

The build environment's network policy blocks every source host. Container HTTPS gets
`CONNECT tunnel failed, response 403` and the WebFetch tool gets `ENOTFOUND`.
As a result:

* `source_documents` is empty and no claim has evidence text.
* No GCC centre, policy or incentive is verified.
* Every company and centre record is an **unverified lead** found through web search.
* No cost, talent or salary observation is stored. Search summaries mentioned figures
  (for example, rents, lease values and headcounts), but a summary is not evidence,
  so none were loaded.
* No corporate relationship is stored. These require filings or annual reports.

**To lift this:** allow the source domains in the environment's network settings, or put
downloaded copies in `data/inbox/<source_key>.pdf|html|txt`, then run
`python -m gcc_atlas.cli ingest`, review the flagged claims, and regenerate the readiness report.

## 2. Coverage gaps even after retrieval

* **Gurugram** relies on a single company (American Express). No official Amex source has been found.
* **Official policy texts** have not been found for Maharashtra, Uttar Pradesh, Haryana,
  Tamil Nadu or Telangana. Only Karnataka's draft is on a government host.
* **Tamil Nadu:** sources disagree on whether it has a GCC policy or a scheme.
* **Telangana:** reports say a GCC policy is still being drafted.
* **Cost data:** real-estate reports give rents by micro-market and grade, as quoted or
  transacted, per month or per year. Comparisons are only allowed within one
  category+unit+period+currency+grade group.
* **Salary data:** no credible public source has been identified yet.
* **Company list:** the 10 companies were chosen for source availability. They are not
  a representative sample of India's GCCs.

## 3. Method limits

* Automated evidence matching looks for a company name and a city in the **same sentence**.
  It can miss evidence in tables or images, and a match still needs human review before a claim is verified.
* Policy matching uses keyword overlap. It confirms that a document is about the policy,
  not what a particular incentive amount is.
* The Research Assistant searches stored records only. It does not generate answers,
  and it is not legal or tax advice.
