-- Issue 05: every Claim and every review points at its own write-once Case
-- file. A correction (a replaced Claim, an invalidated review) is a new file
-- that supersedes it, written by case_file_store; no existing file changes.
ALTER TABLE claims ADD COLUMN case_file text;
ALTER TABLE verifications ADD COLUMN case_file text;
