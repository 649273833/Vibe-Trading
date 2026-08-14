import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { access, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { UpdateRecoveryJournal } from "../dist/update-recovery.js";
import {
  compareSemanticVersions,
  inspectAuthenticodeSignature,
  verifyWindowsUpdateCandidate,
} from "../dist/update-verification.js";

const fixture = Buffer.from("vibe-trading-update-safety-fixture", "utf8");
const fixtureHash = createHash("sha256").update(fixture).digest("hex");
const publisher = "ab".repeat(32);
const otherPublisher = "cd".repeat(32);
const testRoot = await mkdtemp(path.join(os.tmpdir(), "vibe-update-safety-"));
const artifactPath = path.join(testRoot, "candidate.exe");
await writeFile(artifactPath, fixture);

const candidate = { artifactPath, version: "0.3.1", expectedSha256: fixtureHash };
const policy = {
  currentVersion: "0.3.0",
  allowedPublisherCertificateSha256: [publisher],
};
const validSignature = () => ({
  status: "Valid",
  signerSubject: "CN=Vibe-Trading Test Publisher",
  certificateSha256: publisher,
});

const accepted = await verifyWindowsUpdateCandidate(candidate, policy, validSignature);
assert.equal(accepted.accepted, true);

await expectRejection(
  { ...candidate, expectedSha256: "00".repeat(32) },
  policy,
  validSignature,
  "artifact-hash-mismatch",
);
await expectRejection(candidate, policy, () => ({ status: "NotSigned" }), "artifact-unsigned");
await expectRejection(
  candidate,
  policy,
  () => ({ status: "HashMismatch", certificateSha256: publisher }),
  "artifact-signature-invalid",
);
await expectRejection(
  candidate,
  policy,
  () => ({ status: "Valid", certificateSha256: otherPublisher }),
  "publisher-not-allowed",
);
await expectRejection(
  { ...candidate, version: "0.2.9" },
  policy,
  validSignature,
  "version-not-newer",
);
await expectRejection(
  candidate,
  { ...policy, allowedPublisherCertificateSha256: [] },
  validSignature,
  "invalid-verification-policy",
);
await expectRejection(
  candidate,
  { ...policy, allowedPublisherCertificateSha256: [publisher, "malformed"] },
  validSignature,
  "invalid-verification-policy",
);
await expectRejection(
  { ...candidate, artifactPath: path.join(testRoot, "missing.exe") },
  policy,
  validSignature,
  "artifact-inspection-failed",
);

assert.equal(compareSemanticVersions("0.3.1", "0.3.0"), 1);
assert.equal(compareSemanticVersions("0.3.1-beta.2", "0.3.1-beta.1"), 1);
assert.equal(compareSemanticVersions("0.3.1-beta.1", "0.3.1"), -1);
assert.equal(compareSemanticVersions("0.3.0+build.2", "0.3.0+build.1"), 0);
assert.throws(() => compareSemanticVersions("0.3.1-01", "0.3.0"));

let authenticodeAdapterVerified = false;
if (process.platform === "win32") {
  if (!process.env.SystemRoot) throw new Error("SystemRoot is required for the Authenticode adapter test");
  const signedSystemBinary = path.join(
    process.env.SystemRoot,
    "System32",
    "WindowsPowerShell",
    "v1.0",
    "powershell.exe",
  );
  const inspection = inspectAuthenticodeSignature(signedSystemBinary);
  assert.equal(inspection.status, "Valid");
  assert.match(inspection.certificateSha256 || "", /^[a-f0-9]{64}$/u);
  authenticodeAdapterVerified = true;
}

for (const scenario of [
  { phase: "verified", disposition: "discarded-before-shutdown" },
  { phase: "backend-stopped", disposition: "interrupted-before-installer" },
  { phase: "installer-launched", disposition: "installer-failed-or-interrupted" },
]) {
  const directory = await mkdtemp(path.join(testRoot, "recovery-"));
  const journal = new UpdateRecoveryJournal(directory);
  const stagedArtifact = path.join(directory, "update.exe");
  await writeFile(stagedArtifact, fixture);
  let attempt = await journal.begin(newAttempt("update.exe"));
  if (scenario.phase === "backend-stopped" || scenario.phase === "installer-launched") {
    attempt = await journal.advance(attempt.attemptId, "backend-stopped");
  }
  if (scenario.phase === "installer-launched") {
    attempt = await journal.advance(attempt.attemptId, "installer-launched");
  }
  const recovery = await journal.recover("0.3.0");
  assert.equal(recovery.disposition, scenario.disposition);
  assert.equal(await exists(stagedArtifact), false);
  assert.equal(await exists(journal.journalPath), false);
}

const completedDirectory = await mkdtemp(path.join(testRoot, "completed-"));
const completedJournal = new UpdateRecoveryJournal(completedDirectory);
await writeFile(path.join(completedDirectory, "update.exe"), fixture);
await completedJournal.begin(newAttempt("update.exe"));
assert.equal((await completedJournal.recover("0.3.1")).disposition, "completed");

const mismatchDirectory = await mkdtemp(path.join(testRoot, "mismatch-"));
const mismatchJournal = new UpdateRecoveryJournal(mismatchDirectory);
const mismatchArtifact = path.join(mismatchDirectory, "update.exe");
await writeFile(mismatchArtifact, fixture);
await mismatchJournal.begin(newAttempt("update.exe"));
await assert.rejects(() => mismatchJournal.begin(newAttempt("other.exe")), /already exists/u);
assert.equal(
  (await mismatchJournal.recover("0.4.0")).disposition,
  "manual-intervention-required",
);
assert.equal(await exists(mismatchArtifact), true);
assert.equal(await exists(mismatchJournal.journalPath), true);

const traversalDirectory = await mkdtemp(path.join(testRoot, "traversal-"));
const traversalJournal = new UpdateRecoveryJournal(traversalDirectory);
const protectedFile = path.join(testRoot, "protected.exe");
await writeFile(protectedFile, fixture);
await writeFile(traversalJournal.journalPath, JSON.stringify({
  ...newAttempt("../protected.exe"),
  schemaVersion: 1,
  attemptId: "ef".repeat(16),
  phase: "verified",
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
}));
assert.equal(
  (await traversalJournal.recover("0.3.0")).disposition,
  "manual-intervention-required",
);
assert.equal((await readFile(protectedFile)).equals(fixture), true);

console.log(JSON.stringify({
  verificationCases: ["accepted", "tampered", "unsigned", "invalid-signature", "wrong-publisher", "downgraded"],
  recoveryPhases: ["verified", "backend-stopped", "installer-launched", "completed", "version-mismatch", "path-traversal"],
  authenticodeAdapterVerified,
  updaterEnabled: false,
}, null, 2));

async function expectRejection(candidateValue, policyValue, inspector, expectedCode) {
  const result = await verifyWindowsUpdateCandidate(candidateValue, policyValue, inspector);
  assert.equal(result.accepted, false);
  assert.equal(result.code, expectedCode);
}

function newAttempt(artifactFileName) {
  return {
    fromVersion: "0.3.0",
    toVersion: "0.3.1",
    artifactFileName,
    artifactSha256: fixtureHash,
    publisherCertificateSha256: publisher,
  };
}

async function exists(file) {
  try {
    await access(file);
    return true;
  } catch {
    return false;
  }
}
