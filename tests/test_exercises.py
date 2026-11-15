from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from app.main import app

client = TestClient(app)


def test_homepage_exercises_link_describes_the_training_plan():
    response = client.get("/")

    assert response.status_code == 200
    assert 'data-description="腰背、肩胛与肱二头肌训练"' in response.text
    assert 'href="/exercises/"' in response.text


def test_exercises_get_returns_app():
    response = client.get("/exercises/")

    assert response.status_code == 200
    body = response.text
    assert '<h1 id="home-title">腰背、肩胛与肱二头肌训练</h1>' in body
    assert 'id="start-button"' in body
    assert 'id="feedback-form"' in body
    assert 'name="feedback" value="+"' in body
    assert 'name="feedback" value="0"' not in body
    assert 'id="negative-feedback"' in body
    assert 'name="feedback" value="difficulty"' in body
    assert 'name="feedback" value="symptoms"' in body
    assert "/static/exercises/app.js" in body


def test_exercises_head_returns_ok():
    response = client.head("/exercises/")

    assert response.status_code == 200
    assert response.text == ""


def test_legacy_exercises_route_redirects_to_namespace():
    response = client.get("/tools/exercises", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == "/exercises/"


@pytest.fixture
def exercise_page():
    def serve(route):
        path = route.request.url.removeprefix("http://localhost")
        response = client.get(path)
        route.fulfill(
            status=response.status_code,
            content_type=response.headers.get("content-type", "text/plain"),
            body=response.content,
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": 390, "height": 844},
            reduced_motion="reduce",
            timezone_id="America/Toronto",
        )
        page.route("http://localhost/**", serve)
        page.clock.install(time=datetime(2026, 2, 1, 12, tzinfo=timezone.utc))
        yield page
        browser.close()


@pytest.mark.e2e
def test_mobile_exercise_feedback_recovery_undo_and_measurements(exercise_page):
    page = exercise_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://localhost/exercises/")

    expect(page.locator(".plan-group h3")).to_have_text(
        ["Back Exercise", "Shoulder Rehab", "Muscle Building"]
    )
    expect(page.locator(".plan-item")).to_have_count(7)
    assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth")
    page.locator("#voice-toggle").click()

    bridge = page.locator('[data-exercise="glute_bridge"]')
    expect(bridge).to_contain_text("1 组 × 10 次 · 保持 2 秒")
    bridge.get_by_role("button", name="已完成", exact=True).click()
    expect(page.locator("#feedback-choices button")).to_have_count(2)
    expect(page.locator('[value="+"]')).to_contain_text("合适")
    page.locator("#negative-feedback").click()
    expect(page.get_by_role("button", name="太难或控制不佳，且没有不适")).to_be_visible()
    expect(page.get_by_role("button", name="有疼痛、熟悉的不适、麻木或无力")).to_be_visible()
    page.locator("#feedback-back").click()
    page.locator('[value="+"]').click()
    page.locator("#done-button").click()
    expect(bridge).to_contain_text("已确认 0 / 7")
    expect(bridge).to_contain_text("连续 + 1 次")

    page.clock.set_system_time(datetime(2026, 2, 2, 12, tzinfo=timezone.utc))
    page.reload()
    recovery = page.locator(".recovery-row", has_text="臀桥")
    recovery.get_by_role("button", name="无加重").click()
    expect(bridge).to_contain_text("已确认 1 / 7")

    page.locator("#history-button").click()
    expect(page.locator("#history-content")).to_contain_text("恢复无加重")
    page.get_by_role("button", name="撤销反馈").click()
    expect(page.locator("#history-content")).to_contain_text("反馈已撤销")
    page.get_by_role("button", name="重新反馈").click()
    page.locator('[value="+"]').click()
    expect(page.locator("#history-content")).to_contain_text("+ 合适")
    page.locator("#close-history").click()

    page.get_by_label("左上臂（cm）").fill("30.2")
    page.get_by_label("右上臂（cm）").fill("31.1")
    page.get_by_role("button", name="保存围度").click()
    expect(page.locator("#toast")).to_have_text("围度已保存")
    page.reload()
    page.get_by_text("最近 12 周的训练与围度").click()
    expect(page.locator("#experiment-content")).to_contain_text("30.2 / 31.1")
    assert errors == []


@pytest.mark.e2e
def test_mobile_guided_plan_symptom_stop_and_curl_trial(exercise_page):
    page = exercise_page
    page.goto("http://localhost/exercises/")
    page.locator("#voice-toggle").click()
    page.locator("#start-button").click()
    expect(page.locator("#exercise-position")).to_have_text("1 / 6")
    expect(page.locator("#exercise-name")).to_contain_text("Seated Cat-Cow")
    page.locator("#report-symptom").click()
    expect(page.locator("#exercise-name")).to_contain_text("Glute Bridge")
    page.locator("#exit-workout").click()
    page.locator("#confirm-exit").click()

    cat = page.locator('[data-exercise="seated_cat_cow"]')
    expect(cat).to_contain_text("已暂停")
    expect(cat.get_by_role("button", name="开始引导")).to_have_count(0)
    curl = page.locator('[data-exercise="band_curl"]')
    expect(curl).to_contain_text("每侧 2 组 × 8 次")
    curl.get_by_role("button", name="开始试做").click()
    expect(page.locator("#step-instruction")).to_contain_text("每侧 3 次")
    page.locator("#complete-exercise").click()
    page.locator('[value="+"]').click()
    page.locator("#done-button").click()
    expect(curl).to_contain_text("确认试做后的恢复")
    page.clock.set_system_time(datetime(2026, 2, 2, 12, tzinfo=timezone.utc))
    page.reload()
    page.locator(".recovery-row", has_text="坐姿弹力带弯举").get_by_role("button", name="无加重").click()
    expect(curl).to_contain_text("下次")
    expect(curl.get_by_role("button", name="开始引导")).to_have_count(0)
    page.clock.set_system_time(datetime(2026, 2, 3, 12, 1, tzinfo=timezone.utc))
    page.reload()
    expect(curl.get_by_role("button", name="开始引导")).to_be_visible()
    curl.get_by_role("button", name="开始引导").click()
    page.locator("#skip-step-button").click()
    expect(page.locator("#phase-badge")).to_have_text("动作")
    page.locator("#exit-workout").click()
    page.locator("#confirm-exit").click()
    expect(curl.get_by_role("button", name="开始引导")).to_have_count(0)
    expect(curl).to_contain_text("连续 + 0 次")


@pytest.mark.e2e
def test_archived_exercise_is_migrated_and_visible_in_history(exercise_page):
    page = exercise_page
    page.add_init_script(
        """(() => {
            const key = "fengdock.exercises.v1";
            if (localStorage.getItem(key)) return;
            localStorage.setItem(key, JSON.stringify({
                version: 2, levels: {static_plank: 4},
                sessions: [{
                    id: "previous", timestamp: "2026-01-01T12:00:00.000Z",
                    records: [{
                        exercise_id: "static_plank", level: 4, feedback: "good",
                        completed: true, prescribed_dose: {sets: 3, holdSeconds: 45}
                    }]
                }]
            }));
        })();"""
    )
    page.goto("http://localhost/exercises/")
    expect(page.locator(".plan-item")).to_have_count(7)
    expect(page.locator("#plan-list")).not_to_contain_text("Static Plank")
    page.locator("#history-button").click()
    history = page.locator("#history-content")
    expect(history).to_contain_text("Static Plank · 平板支撑 · 已归档 · L4")
    expect(history).to_contain_text("保持 45 秒")
    expect(history).to_contain_text("没问题")
    page.wait_for_function(
        """() => JSON.parse(localStorage.getItem("fengdock.exercises.v1")).version === 4"""
    )


@pytest.mark.e2e
def test_cat_cow_phases_count_down_and_reuse_downloads(exercise_page):
    page = exercise_page
    page.add_init_script(
        """{
            window.exerciseAudio = [];
            window.exerciseClipsDecoded = 0;
            const decode = AudioContext.prototype.decodeAudioData;
            AudioContext.prototype.decodeAudioData = async function (...args) {
                const buffer = await decode.apply(this, args);
                window.exerciseClipsDecoded += 1;
                return buffer;
            };
            const start = AudioBufferSourceNode.prototype.start;
            AudioBufferSourceNode.prototype.start = function (...args) {
                window.exerciseAudio.push(this.buffer.duration);
                return start.apply(this, args);
            };
        }"""
    )
    requested = []
    page.on("request", lambda request: requested.append(request.url) if request.url.endswith(".mp3") else None)
    with page.expect_response(lambda response: "/cat_cow_arch." in response.url):
        page.goto("http://localhost/exercises/")
    page.wait_for_function(
        r"""() => new Promise(resolve => {
            const request = indexedDB.open("fengdock-exercise-clips", 1);
            request.onsuccess = () => {
                const database = request.result;
                const store = database.transaction("clips").objectStore("clips");
                const keys = store.getAllKeys();
                keys.onsuccess = () => {
                    database.close();
                    resolve(keys.result.filter(key => /^(cat_cow_(cat|arch)|countdown_[123])\./.test(key)).length === 5);
                };
                keys.onerror = () => resolve(false);
            };
            request.onerror = () => resolve(false);
        })"""
    )

    def check_cat_cow_cues():
        page.locator('[data-exercise="seated_cat_cow"]').get_by_role("button", name="开始引导").click()
        page.wait_for_function("window.exerciseClipsDecoded >= 5")
        page.clock.run_for(8100)
        expect(page.locator("#step-instruction")).to_contain_text("猫式")
        expect(page.locator("#round-label")).to_contain_text("第 1/8 次")
        first_phase_end = page.evaluate("window.exerciseAudio.length")
        page.clock.run_for(5000)
        countdown = page.evaluate("start => window.exerciseAudio.slice(start)", first_phase_end)
        assert len(countdown) == 3 and all(length < 1 for length in countdown)
        page.clock.run_for(1000)
        expect(page.locator("#step-instruction")).to_contain_text("牛式")
        expect(page.locator("#round-label")).to_contain_text("第 1/8 次")
        assert page.evaluate("window.exerciseAudio.some(duration => duration > 2.5)")
        page.clock.run_for(3000)
        assert page.evaluate("window.exerciseAudio.at(-1)") < 1

    check_cat_cow_cues()
    for cue in ("cat_cow_cat", "cat_cow_arch", "countdown_3"):
        assert sum(f"/{cue}." in url for url in requested) == 1
    requested.clear()
    page.reload()
    check_cat_cow_cues()
    assert requested == []
