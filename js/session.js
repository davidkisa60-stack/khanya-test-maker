(function (w) {
    var IDLE_MS = 5 * 60 * 1000;
    var last = Date.now();
    var gone = false;

    function getUser() {
        try {
            return JSON.parse(localStorage.getItem('khanya_user') || 'null');
        } catch (e) {
            return null;
        }
    }

    function headers() {
        var u = getUser() || {};
        var h = {
            'Content-Type': 'application/json',
            'X-User-Email': u.email || ''
        };
        if (u.token) {
            h['Authorization'] = 'Bearer ' + u.token;
            h['X-Session-Token'] = u.token;
        }
        return h;
    }

    function toLogin(reason) {
        if (gone) return;
        gone = true;
        localStorage.removeItem('khanya_user');
        sessionStorage.clear();
        var q = reason ? ('?reason=' + encodeURIComponent(reason)) : '';
        w.location.replace('login.html' + q);
    }

    function logoutServer(done) {
        var u = getUser();
        var token = u && u.token;
        fetch('/api/logout', {
            method: 'POST',
            headers: headers(),
            body: JSON.stringify({ token: token || '' })
        }).catch(function () {}).finally(function () {
            if (done) done();
        });
    }

    function kick(reason) {
        logoutServer(function () { toLogin(reason); });
    }

    function heartbeat() {
        if (Date.now() - last > IDLE_MS) {
            kick('idle');
            return;
        }
        // Only ping the server while the user is actually using the page.
        if (Date.now() - last > 25000) return;
        var u = getUser();
        if (!u || !u.token) {
            toLogin('session');
            return;
        }
        fetch('/api/session', {
            method: 'POST',
            headers: headers(),
            body: JSON.stringify({ token: u.token })
        }).then(function (res) {
            return res.json().then(function (d) { return { ok: res.ok, d: d }; });
        }).then(function (x) {
            if (!x.ok) kick(x.d && x.d.reason ? x.d.reason : 'session');
        }).catch(function () {});
    }

    function touch() {
        last = Date.now();
    }

    function start() {
        var u = getUser();
        if (!u || !u.token) {
            toLogin('session');
            return;
        }
        ['click', 'keydown', 'mousemove', 'scroll', 'touchstart'].forEach(function (ev) {
            w.addEventListener(ev, touch, { passive: true });
        });
        setInterval(function () {
            if (Date.now() - last > IDLE_MS) kick('idle');
        }, 4000);
        heartbeat();
        setInterval(heartbeat, 20000);
    }

    function logoutNow() {
        logoutServer(function () { toLogin(''); });
    }

    w.khanyaAuth = {
        getUser: getUser,
        headers: headers,
        start: start,
        kick: kick,
        logoutNow: logoutNow,
        toLogin: toLogin
    };
})(window);
