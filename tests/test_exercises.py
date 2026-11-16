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
    assert 'name="feedback" value="-"' in body
    assert 'id="recovery-panel"' not in body
    assert 'id="measurement-form"' not in body
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
def test_mobile_exercise_feedback_has_two_options_and_no_followup(exercise_page):
    page = exercise_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://localhost/exercises/")
    expect(page.locator(".plan-group h3")).to_have_text(["站姿", "仰卧", "坐姿"])
    expect(page.locator(".plan-item")).to_have_count(7)
    assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth")
    page.locator("#voice-toggle").click()

    bridge = page.locator('[data-exercise="glute_bridge"]')
    bridge.get_by_role("button", name="已完成", exact=True).click()
    expect(page.locator("#feedback-choices button")).to_have_count(2)
    expect(page.locator('[value="+"]')).to_contain_text("合适")
    expect(page.locator('[value="-"]')).to_contain_text("不合适")
    page.locator('[value="-"]').click()
    page.locator("#done-button").click()
    expect(bridge).to_contain_text("已暂停")

    page.clock.set_system_time(datetime(2026, 2, 2, 12, tzinfo=timezone.utc))
    page.reload()
    expect(page.locator("#home-view")).not_to_contain_text("恢复确认")
    expect(page.locator("#home-view")).not_to_contain_text("症状加重")
    expect(page.locator("#home-view")).not_to_contain_text("上臂围度")
    page.locator("#history-button").click()
    expect(page.locator("#history-content")).to_contain_text("− 不合适")
    expect(page.locator("#history-content")).not_to_contain_text("报告加重")
    page.get_by_role("button", name="撤销反馈").click()
    page.get_by_role("button", name="重新反馈").click()
    page.locator('[value="+"]').click()
    expect(page.locator("#history-content")).to_contain_text("+ 合适")
    page.locator("#close-history").click()
    expect(bridge).to_contain_text("进阶进度 1 / 7")
    assert errors == []


@pytest.mark.e2e
def test_one_workout_starts_six_or_seven_exercises_with_formal_curl_last(exercise_page):
    page = exercise_page
    page.clock.set_system_time(datetime(2026, 2, 2, 12, tzinfo=timezone.utc))
    page.goto("http://localhost/exercises/")
    page.locator("#voice-toggle").click()
    curl = page.locator('[data-exercise="band_curl"]')
    expect(curl).to_contain_text("每侧 2 组 × 8 次")
    expect(curl.locator("button")).to_have_count(0)

    start = page.locator("#start-button")
    skip = page.locator("#skip-exercise-button")
    start.click()
    for display_index, name in enumerate([
        "Wall Slide", "Glute Bridge", "Supine March", "Supine Serratus Punch",
        "Seated Cat-Cow", "Shoulder Rolls", "Seated Resistance Band Biceps Curl",
    ], start=1):
        expect(page.locator("#exercise-position")).to_have_text(f"{display_index} / 7")
        expect(page.locator("#exercise-name")).to_contain_text(name)
        if display_index < 7:
            skip.click()
    expect(page.locator("#step-instruction")).not_to_contain_text("试做")
    page.locator("#complete-exercise").click()
    page.locator('[value="+"]').click()
    page.locator("#done-button").click()

    for day, count in [(3, 6), (5, 7)]:
        page.clock.set_system_time(datetime(2026, 2, day, 12, 5, tzinfo=timezone.utc))
        page.reload()
        expect(start).to_contain_text(f"{count} 个动作")
        start.click()
        expect(page.locator("#exercise-position")).to_have_text(f"1 / {count}")


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
        """() => JSON.parse(localStorage.getItem("fengdock.exercises.v1")).version === 5"""
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
                window.exerciseAudio.push((args[2] ?? this.buffer.duration) / this.playbackRate.value);
                return start.apply(this, args);
            };
        }"""
    )
    clip_count = len(client.get("/static/exercises/audio/manifest.json").json()["cues"])
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
        page.wait_for_function("count => window.exerciseClipsDecoded === count", arg=clip_count)
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
        assert page.evaluate("window.exerciseAudio.at(-1)") > 1
        page.clock.run_for(3000)
        assert page.evaluate("window.exerciseAudio.at(-1)") < 1

    check_cat_cow_cues()
    for cue in ("cat_cow_cat", "cat_cow_arch", "countdown_3"):
        assert sum(f"/{cue}." in url for url in requested) == 1
    requested.clear()
    page.reload()
    check_cat_cow_cues()
    assert requested == []


    page.reload()
    wall = page.locator('[data-exercise="wall_slide"]')
    wall.get_by_role("button", name="开始引导").click()
    page.wait_for_function("count => window.exerciseClipsDecoded === count", arg=clip_count)
    page.clock.run_for(8100)
    expect(page.locator("#step-instruction")).to_contain_text("手沿墙上滑")
    before = page.evaluate("window.exerciseAudio.length")
    page.clock.run_for(4000)
    countdown = page.evaluate("start => window.exerciseAudio.slice(start)", before)
    assert len(countdown) == 3 and all(length < 1 for length in countdown)

    page.reload()
    march = page.locator('[data-exercise="supine_march"]')
    march.get_by_role("button", name="开始引导").click()
    advance = page.locator("#skip-step-button")
    advance.click()
    expect(page.locator("#step-instruction")).to_contain_text("左侧 · 轻抬一脚")
    advance.click()
    expect(page.locator("#step-instruction")).to_contain_text("左侧 · 保持 2 秒")
    advance.click()
    expect(page.locator("#step-instruction")).to_contain_text("左侧 · 缓慢回位")
    advance.click()
    expect(page.locator("#step-instruction")).to_contain_text("右侧 · 轻抬一脚")


    for exercise_id, expected_steps, first_rep in [
        ("shoulder_rolls", ("向前", "向后"), 4),
        ("serratus_punch", ("左侧", "右侧"), 4),
    ]:
        page.reload()
        exercise = page.locator(f'[data-exercise="{exercise_id}"]')
        exercise.get_by_role("button", name="开始引导").click()
        page.wait_for_function("count => window.exerciseClipsDecoded === count", arg=clip_count)
        page.clock.run_for(8100)
        expect(page.locator("#step-instruction")).to_contain_text(expected_steps[0])
        expect(page.locator("#countdown")).to_have_text(str(first_rep))
        start_index = page.evaluate("window.exerciseAudio.length")
        page.clock.run_for(3000)
        spoken = page.evaluate("start => window.exerciseAudio.slice(start)", start_index)
        assert len(spoken) == 3 and all(length < 1 for length in spoken)
        if exercise_id == "shoulder_rolls":
            page.clock.run_for(17000)
            expect(page.locator("#step-instruction")).to_contain_text("向后")
            expect(page.locator("#countdown")).to_have_text("4")
            start_index = page.evaluate("window.exerciseAudio.length")
            page.clock.run_for(3000)
            spoken = page.evaluate("start => window.exerciseAudio.slice(start)", start_index)
            assert len(spoken) == 3 and all(length < 1 for length in spoken)
