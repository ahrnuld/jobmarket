// Owner-specific settings. Fill these in before launch (TR-07, TR-08).

export const siteConfig = {
  /** Shown on the About page as owner and funder (TR-07). null = placeholder text is shown. */
  ownerName: "Mark de Haan",
  /** Public contact address, optional. */
  contactEmail: "mark.dehaan@inholland.nl",
  /**
   * Where the error-report form sends reports (TR-08). One of:
   *   { type: "github", repo: "owner/name" }  -> opens a pre-filled GitHub issue
   *   { type: "email", address: "..." }        -> opens the visitor's mail program
   *   null                                      -> form shown as not yet active
   */
  reportTarget: null as null | { type: "github"; repo: string } | { type: "email"; address: string },
  /**
   * Licence for the downloadable aggregates (FR-11), e.g. "CC BY 4.0". null = the data page says
   * the licence is not decided yet. Check first that the source terms (Adzuna) allow it.
   */
  dataLicence: null as string | null,
  /** Source code repository, if public. */
  repositoryUrl: null as string | null,
};
