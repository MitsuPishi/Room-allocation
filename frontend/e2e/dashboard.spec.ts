import { expect, test } from "@playwright/test";

const session = {
  username: "admin",
  must_change_password: false,
  csrf_token: "test-csrf",
};

const completedRun = {
  id: "run-1",
  dataset_id: "dataset-1",
  dataset_filename: "students.xlsx",
  student_count: 120,
  status: "succeeded",
  configuration: { capacity_mode: "mixed", capacity: 6, capacity_mix: [{ count: 20, capacity: 6 }], time_limit_seconds: 300, seed: 42, restarts: 3, cp_sat_enabled: false },
  scoring_configuration: {},
  progress: { phase: "completed", message: "تخصیص با موفقیت تکمیل شد" },
  metrics: { min_student_utility: 81.2, p10_room_quality: 84.5, mean_student_utility: 90.1 },
  metadata: { room_inventory: { assigned_rooms: 20, unused_rooms: 0, active_vacancies: 0, occupied_beds: 120 } },
  artifacts: Object.fromEntries(["unimate_report.xlsx", "unimate_report.pdf", "assignments.csv", "room_metrics.csv", "student_metrics.csv", "validation_report.csv", "run_metadata.json"].map((name) => [name, { size: 2048, sha256: "a".repeat(64), storage_key: `artifacts/run-1/${name}` }])),
  error_message: null,
  cancel_requested: false,
  created_at: "2026-08-10T08:00:00Z",
  queued_at: "2026-08-10T08:00:01Z",
  started_at: "2026-08-10T08:00:02Z",
  completed_at: "2026-08-10T08:01:00Z",
  runtime_seconds: 58,
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: session }));
  await page.route("**/api/config", (route) => route.fulfill({ json: { upload_limit_mb: 25 } }));
  await page.route("**/api/runs/run-1/analytics**", (route) => route.fulfill({ json: { rooms: [], student_utilities: [], search_history: [] } }));
  await page.route("**/api/runs", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    return route.fallback();
  });
});

test("renders the Persian RTL operations dashboard", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { name: "اجراهای تخصیص اتاق" })).toBeVisible();
  await expect(page.getByText("هنوز اجرایی ثبت نشده است")).toBeVisible();
  await expect(page.getByText("سرویس فعال")).toBeVisible();
});

test("renders a non-empty run history without crashing", async ({ page }) => {
  await page.route("**/api/runs", (route) => route.fulfill({ json: [completedRun] }));
  await page.goto("/");
  await expect(page.getByText("students.xlsx")).toBeVisible();
  await expect(page.getByText("۱ نوع اتاق")).toBeVisible();
  await expect(page.getByRole("link", { name: "مشاهده اجرا" })).toBeVisible();
});

test("validates an uploaded survey before showing inventory settings", async ({ page }) => {
  await page.route("**/api/datasets", (route) => route.fulfill({
    status: 201,
    json: {
      id: "dataset-1",
      original_filename: "students.csv",
      row_count: 120,
      is_valid: true,
      error_count: 0,
      warning_count: 1,
      validation_issues: [{ severity: "warning", field: "age", message: "ستون سن اختیاری است." }],
      created_at: "2026-08-10T08:00:00Z",
    },
  }));
  await page.goto("/runs/new");
  await page.locator('input[type="file"]').setInputFiles({
    name: "students.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("student_id,cleanliness\n1,1"),
  });
  await expect(page.getByText("students.csv")).toBeVisible();
  await page.getByRole("button", { name: /ادامه تنظیمات/ }).click();
  await expect(page.getByRole("heading", { name: "موجودی اتاق و سیاست اجرا" })).toBeVisible();
  await page.getByRole("button", { name: "ظرفیت متغیر" }).click();
  await expect(page.getByText("ظرفیت کل موجودی")).toBeVisible();
});

test("blocks the wizard when questionnaire validation fails", async ({ page }) => {
  await page.route("**/api/datasets", (route) => route.fulfill({
    status: 201,
    json: {
      id: "dataset-invalid",
      original_filename: "invalid.csv",
      row_count: 2,
      is_valid: false,
      error_count: 1,
      warning_count: 0,
      validation_issues: [{ severity: "error", field: "student_id", message: "شناسه دانشجو الزامی است." }],
      created_at: "2026-08-10T08:00:00Z",
    },
  }));
  await page.goto("/runs/new");
  await page.locator('input[type="file"]').setInputFiles({ name: "invalid.csv", mimeType: "text/csv", buffer: Buffer.from("student_id\n") });
  await expect(page.getByText("شناسه دانشجو الزامی است.")).toBeVisible();
  await expect(page.getByRole("button", { name: /ادامه تنظیمات/ })).toBeDisabled();
});

test("keeps result queries run-scoped and exposes every audited export", async ({ page }) => {
  await page.route("**/api/runs/run-1", (route) => route.fulfill({ json: completedRun }));
  await page.route("**/api/runs/run-1/rooms?**", (route) => route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 50 } }));
  await page.route("**/api/audit?entity_id=run-1&limit=200", (route) => route.fulfill({ json: { items: [{ id: 1, action: "run_completed", entity_type: "run", entity_id: "run-1", details: {}, created_at: completedRun.completed_at }], total: 1, offset: 0, limit: 200 } }));
  await page.route("**/api/runs/run-1/artifacts/assignments.csv", (route) => route.fulfill({ body: "room_id,student_id\nB-401,S-001\n", headers: { "Content-Type": "text/csv", "Content-Disposition": "attachment; filename=assignments.csv" } }));

  await page.goto("/runs/run-1");
  await page.getByRole("button", { name: "اتاق‌ها" }).click();
  await page.getByPlaceholder("جست‌وجوی شناسه اتاق").fill("B-401");
  await expect.poll(() => page.evaluate(() => performance.getEntriesByType("resource").map((item) => item.name).some((name) => name.includes("/api/runs/run-1/rooms?query=B-401")))).toBeTruthy();

  await page.getByRole("button", { name: "تاریخچه" }).click();
  await expect(page.getByText("تاریخچه این اجرا")).toBeVisible();
  await page.getByRole("button", { name: "خروجی‌ها" }).click();
  await expect(page.locator(".export-card")).toHaveCount(7);
  const download = page.waitForEvent("download");
  await page.getByText("فهرست تخصیص دانشجویان").click();
  await expect((await download).suggestedFilename()).toBe("assignments.csv");
});

test("drills into room composition and student preferences", async ({ page }) => {
  const students = [
    { room_id: "B-401", bed: 1, room_capacity: 3, student_idx: 0, student_id: "S-001", student_name: "مریم احمدی", student_utility: 91.5, room_quality: 88.2, faculty: "فنی", major: "مهندسی کامپیوتر", age: 21, sleep_window: 1, wake_window: 2, noise_tolerance: 0, study_habit: 1, cleanliness: 1 },
    { room_id: "B-401", bed: 2, room_capacity: 3, student_idx: 1, student_id: "S-002", student_name: "سارا رضایی", student_utility: 86.4, room_quality: 88.2, faculty: "علوم", major: "ریاضی", age: 22, sleep_window: 1, wake_window: 2, noise_tolerance: 0, study_habit: 1, cleanliness: 1 },
  ];
  await page.route("**/api/runs/run-1", (route) => route.fulfill({ json: completedRun }));
  await page.route("**/api/runs/run-1/rooms?**", (route) => route.fulfill({ json: { items: [{ room_id: "B-401", room_size: 2, room_capacity: 3, room_quality: 88.2, mean_student_utility: 89, cleanliness_contribution: 25, noise_contribution: 25, study_contribution: 25, schedule_contribution: 13.2 }], total: 1, offset: 0, limit: 50 } }));
  await page.route("**/api/runs/run-1/students?**", (route) => route.fulfill({ json: { items: students, total: students.length, offset: 0, limit: 50 } }));

  await page.goto("/runs/run-1");
  await page.getByRole("button", { name: "اتاق‌ها" }).click();
  await expect(page.getByText("قوی‌ترین معیار")).toBeVisible();
  await page.getByRole("button", { name: "جزئیات" }).click();
  await expect(page.getByRole("dialog", { name: "اتاق B-401" })).toBeVisible();
  await expect(page.getByText("اجزای کیفیت اتاق")).toBeVisible();
  await expect(page.getByText("مریم احمدی")).toBeVisible();
  await page.getByRole("button", { name: "بستن جزئیات" }).click();

  await page.getByRole("button", { name: "دانشجویان" }).click();
  await expect(page.getByText("خلاصه ترجیحات")).toBeVisible();
  await page.getByRole("button", { name: "مشاهده" }).first().click();
  await expect(page.getByRole("dialog", { name: "مریم احمدی" })).toBeVisible();
  await expect(page.getByText("پروفایل و ترجیحات")).toBeVisible();
  await expect(page.getByText("مهندسی کامپیوتر", { exact: true })).toBeVisible();
  await expect(page.getByText("ترکیب هم‌اتاقی‌ها")).toBeVisible();
});

test("requires confirmation before deleting a completed run", async ({ page }) => {
  await page.route("**/api/runs/run-1", async (route) => {
    if (route.request().method() === "DELETE") return route.fulfill({ status: 204 });
    return route.fulfill({ json: completedRun });
  });
  page.once("dialog", (dialog) => dialog.accept());
  await page.goto("/runs/run-1");
  await page.getByRole("button", { name: "حذف" }).click();
  await expect(page).toHaveURL(/\/$/);
});
