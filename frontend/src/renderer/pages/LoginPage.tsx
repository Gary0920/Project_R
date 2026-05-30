import { FormEvent, useState, useRef, useEffect, useCallback } from "react";
import { useAtomValue, useSetAtom } from "jotai";

import { apiRequest, ApiError } from "../api/client";
import type { LoginResponse } from "../api/types";
import { setAuthAtom } from "../atoms/auth-atoms";
import { serverUrlAtom } from "../atoms/server-atoms";
import { APP_NAME } from "../constants/app";

/* ------------------------------------------------------------------ */
/*  Animation helpers (pure functions, no React deps)                   */
/* ------------------------------------------------------------------ */

function calcPosition(el: HTMLElement | null, mouseX: number, mouseY: number) {
  if (!el) return { faceX: 0, faceY: 0, bodySkew: 0 };
  const rect = el.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 3;
  const dx = mouseX - cx;
  const dy = mouseY - cy;
  const faceX = Math.max(-15, Math.min(15, dx / 20));
  const faceY = Math.max(-10, Math.min(10, dy / 30));
  const bodySkew = Math.max(-6, Math.min(6, -dx / 120));
  return { faceX, faceY, bodySkew };
}

function calcPupilOffset(
  el: HTMLElement | null,
  mouseX: number,
  mouseY: number,
  maxDist: number,
) {
  if (!el) return { x: 0, y: 0 };
  const rect = el.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const dx = mouseX - cx;
  const dy = mouseY - cy;
  const dist = Math.min(Math.sqrt(dx * dx + dy * dy), maxDist);
  const angle = Math.atan2(dy, dx);
  return { x: Math.cos(angle) * dist, y: Math.sin(angle) * dist };
}

/* ------------------------------------------------------------------ */
/*  Storage helpers                                                     */
/* ------------------------------------------------------------------ */

const LAST_USERNAME_KEY = "project-r:last-username";
const REMEMBER_PASSWORD_KEY = "project-r:remember-password";
const STORED_PASSWORD_KEY = "project-r:stored-password";

function encodePwd(pwd: string): string {
  return btoa(encodeURIComponent(pwd));
}

function decodePwd(encoded: string): string {
  return decodeURIComponent(atob(encoded));
}

/* ------------------------------------------------------------------ */
/*  Component                                                           */
/* ------------------------------------------------------------------ */

export function LoginPage() {
  /* ---------- Form state ---------- */
  const serverUrl = useAtomValue(serverUrlAtom);
  const setAuth = useSetAtom(setAuthAtom);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [rememberPassword, setRememberPassword] = useState(() => {
    return window.localStorage.getItem(REMEMBER_PASSWORD_KEY) === "true";
  });

  /* ---------- Load saved credentials ---------- */
  useEffect(() => {
    const savedUsername = window.localStorage.getItem(LAST_USERNAME_KEY);
    if (savedUsername) {
      setUsername(savedUsername);
    }
    if (window.localStorage.getItem(REMEMBER_PASSWORD_KEY) === "true") {
      const savedPassword = window.localStorage.getItem(STORED_PASSWORD_KEY);
      if (savedPassword) {
        try {
          setPassword(decodePwd(savedPassword));
        } catch {
          // 忽略损坏的存储数据
        }
      }
      setRememberPassword(true);
    }
  }, []);

  /* ---------- Character DOM refs ---------- */
  const charPurpleRef = useRef<HTMLDivElement>(null);
  const charBlackRef = useRef<HTMLDivElement>(null);
  const charOrangeRef = useRef<HTMLDivElement>(null);
  const charYellowRef = useRef<HTMLDivElement>(null);

  const purpleEyesRef = useRef<HTMLDivElement>(null);
  const purpleEyeLRef = useRef<HTMLDivElement>(null);
  const purpleEyeRRef = useRef<HTMLDivElement>(null);
  const purplePupilLRef = useRef<HTMLDivElement>(null);
  const purplePupilRRef = useRef<HTMLDivElement>(null);

  const blackEyesRef = useRef<HTMLDivElement>(null);
  const blackEyeLRef = useRef<HTMLDivElement>(null);
  const blackEyeRRef = useRef<HTMLDivElement>(null);
  const blackPupilLRef = useRef<HTMLDivElement>(null);
  const blackPupilRRef = useRef<HTMLDivElement>(null);

  const orangeEyesRef = useRef<HTMLDivElement>(null);
  const orangePupilLRef = useRef<HTMLDivElement>(null);
  const orangePupilRRef = useRef<HTMLDivElement>(null);
  const orangeMouthRef = useRef<HTMLDivElement>(null);

  const yellowEyesRef = useRef<HTMLDivElement>(null);
  const yellowPupilLRef = useRef<HTMLDivElement>(null);
  const yellowPupilRRef = useRef<HTMLDivElement>(null);
  const yellowMouthRef = useRef<HTMLDivElement>(null);

  const passwordInputRef = useRef<HTMLInputElement>(null);

  /* ---------- Mutable animation state (no re-renders) ---------- */
  const anim = useRef({
    mouseX: 0,
    mouseY: 0,
    isTyping: false,
    isLookingAtEachOther: false,
    isPasswordFocused: false,
    isPurpleBlinking: false,
    isBlackBlinking: false,
    isPurplePeeking: false,
    isLoginError: false,
    showPassword: false,
  });

  /* ---------- Timer refs ---------- */
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const errorRecoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shakeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const peekTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const purpleBlinkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const blackBlinkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* ---------- React state for CSS classes ---------- */
  const [shakeHead, setShakeHead] = useState(false);
  const [showOrangeMouth, setShowOrangeMouth] = useState(false);

  /* ---------------------------------------------------------------- */
  /*  updateCharacters                                                */
  /* ---------------------------------------------------------------- */
  const updateCharacters = useCallback(() => {
    const a = anim.current;
    const purplePos = calcPosition(charPurpleRef.current, a.mouseX, a.mouseY);
    const blackPos = calcPosition(charBlackRef.current, a.mouseX, a.mouseY);
    const orangePos = calcPosition(charOrangeRef.current, a.mouseX, a.mouseY);
    const yellowPos = calcPosition(charYellowRef.current, a.mouseX, a.mouseY);

    const pwdLen = passwordInputRef.current?.value.length ?? 0;
    const isShowingPwd = pwdLen > 0 && a.showPassword;
    const isLookingAway = a.isPasswordFocused && !a.showPassword;

    /* ---- Purple ---- */
    if (charPurpleRef.current) {
      if (isShowingPwd) {
        charPurpleRef.current.style.transform = "skewX(0deg)";
        charPurpleRef.current.style.height = "370px";
      } else if (isLookingAway) {
        charPurpleRef.current.style.transform = "skewX(-14deg) translateX(-20px)";
        charPurpleRef.current.style.height = "410px";
      } else if (a.isTyping) {
        charPurpleRef.current.style.transform = `skewX(${(purplePos.bodySkew || 0) - 12}deg) translateX(40px)`;
        charPurpleRef.current.style.height = "410px";
      } else {
        charPurpleRef.current.style.transform = `skewX(${purplePos.bodySkew}deg)`;
        charPurpleRef.current.style.height = "370px";
      }
    }

    if (purpleEyeLRef.current)
      purpleEyeLRef.current.style.height = a.isPurpleBlinking ? "2px" : "18px";
    if (purpleEyeRRef.current)
      purpleEyeRRef.current.style.height = a.isPurpleBlinking ? "2px" : "18px";

    if (
      purpleEyesRef.current &&
      purplePupilLRef.current &&
      purplePupilRRef.current
    ) {
      if (a.isLoginError) {
        purpleEyesRef.current.style.left = "30px";
        purpleEyesRef.current.style.top = "55px";
        purplePupilLRef.current.style.transform = "translate(-3px, 4px)";
        purplePupilRRef.current.style.transform = "translate(-3px, 4px)";
      } else if (isLookingAway) {
        purpleEyesRef.current.style.left = "20px";
        purpleEyesRef.current.style.top = "25px";
        purplePupilLRef.current.style.transform = "translate(-5px, -5px)";
        purplePupilRRef.current.style.transform = "translate(-5px, -5px)";
      } else if (isShowingPwd) {
        purpleEyesRef.current.style.left = "20px";
        purpleEyesRef.current.style.top = "35px";
        const px = a.isPurplePeeking ? 4 : -4;
        const py = a.isPurplePeeking ? 5 : -4;
        purplePupilLRef.current.style.transform = `translate(${px}px, ${py}px)`;
        purplePupilRRef.current.style.transform = `translate(${px}px, ${py}px)`;
      } else if (a.isLookingAtEachOther) {
        purpleEyesRef.current.style.left = "55px";
        purpleEyesRef.current.style.top = "65px";
        purplePupilLRef.current.style.transform = "translate(3px, 4px)";
        purplePupilRRef.current.style.transform = "translate(3px, 4px)";
      } else {
        purpleEyesRef.current.style.left = `${45 + purplePos.faceX}px`;
        purpleEyesRef.current.style.top = `${40 + purplePos.faceY}px`;
        const po = calcPupilOffset(purpleEyeLRef.current, a.mouseX, a.mouseY, 5);
        purplePupilLRef.current.style.transform = `translate(${po.x}px, ${po.y}px)`;
        purplePupilRRef.current.style.transform = `translate(${po.x}px, ${po.y}px)`;
      }
    }

    /* ---- Black ---- */
    if (charBlackRef.current) {
      if (isShowingPwd) {
        charBlackRef.current.style.transform = "skewX(0deg)";
      } else if (isLookingAway) {
        charBlackRef.current.style.transform = "skewX(12deg) translateX(-10px)";
      } else if (a.isLookingAtEachOther) {
        charBlackRef.current.style.transform = `skewX(${(blackPos.bodySkew || 0) * 1.5 + 10}deg) translateX(20px)`;
      } else if (a.isTyping) {
        charBlackRef.current.style.transform = `skewX(${(blackPos.bodySkew || 0) * 1.5}deg)`;
      } else {
        charBlackRef.current.style.transform = `skewX(${blackPos.bodySkew}deg)`;
      }
    }

    if (blackEyeLRef.current)
      blackEyeLRef.current.style.height = a.isBlackBlinking ? "2px" : "16px";
    if (blackEyeRRef.current)
      blackEyeRRef.current.style.height = a.isBlackBlinking ? "2px" : "16px";

    if (
      blackEyesRef.current &&
      blackPupilLRef.current &&
      blackPupilRRef.current
    ) {
      if (a.isLoginError) {
        blackEyesRef.current.style.left = "15px";
        blackEyesRef.current.style.top = "40px";
        blackPupilLRef.current.style.transform = "translate(-3px, 4px)";
        blackPupilRRef.current.style.transform = "translate(-3px, 4px)";
      } else if (isLookingAway) {
        blackEyesRef.current.style.left = "10px";
        blackEyesRef.current.style.top = "20px";
        blackPupilLRef.current.style.transform = "translate(-4px, -5px)";
        blackPupilRRef.current.style.transform = "translate(-4px, -5px)";
      } else if (isShowingPwd) {
        blackEyesRef.current.style.left = "10px";
        blackEyesRef.current.style.top = "28px";
        blackPupilLRef.current.style.transform = "translate(-4px, -4px)";
        blackPupilRRef.current.style.transform = "translate(-4px, -4px)";
      } else if (a.isLookingAtEachOther) {
        blackEyesRef.current.style.left = "32px";
        blackEyesRef.current.style.top = "12px";
        blackPupilLRef.current.style.transform = "translate(0px, -4px)";
        blackPupilRRef.current.style.transform = "translate(0px, -4px)";
      } else {
        blackEyesRef.current.style.left = `${26 + blackPos.faceX}px`;
        blackEyesRef.current.style.top = `${32 + blackPos.faceY}px`;
        const bo = calcPupilOffset(blackEyeLRef.current, a.mouseX, a.mouseY, 4);
        blackPupilLRef.current.style.transform = `translate(${bo.x}px, ${bo.y}px)`;
        blackPupilRRef.current.style.transform = `translate(${bo.x}px, ${bo.y}px)`;
      }
    }

    /* ---- Orange ---- */
    if (orangeMouthRef.current) {
      if (a.isLoginError) {
        orangeMouthRef.current.style.left = `${80 + orangePos.faceX}px`;
        orangeMouthRef.current.style.top = "130px";
      }
    }
    if (charOrangeRef.current) {
      if (isShowingPwd) {
        charOrangeRef.current.style.transform = "skewX(0deg)";
      } else {
        charOrangeRef.current.style.transform = `skewX(${orangePos.bodySkew}deg)`;
      }
    }

    if (
      orangeEyesRef.current &&
      orangePupilLRef.current &&
      orangePupilRRef.current
    ) {
      if (a.isLoginError) {
        orangeEyesRef.current.style.left = "60px";
        orangeEyesRef.current.style.top = "95px";
        orangePupilLRef.current.style.transform = "translate(-3px, 4px)";
        orangePupilRRef.current.style.transform = "translate(-3px, 4px)";
      } else if (isLookingAway) {
        orangeEyesRef.current.style.left = "50px";
        orangeEyesRef.current.style.top = "75px";
        orangePupilLRef.current.style.transform = "translate(-5px, -5px)";
        orangePupilRRef.current.style.transform = "translate(-5px, -5px)";
      } else if (isShowingPwd) {
        orangeEyesRef.current.style.left = "50px";
        orangeEyesRef.current.style.top = "85px";
        orangePupilLRef.current.style.transform = "translate(-5px, -4px)";
        orangePupilRRef.current.style.transform = "translate(-5px, -4px)";
      } else {
        orangeEyesRef.current.style.left = `${82 + orangePos.faceX}px`;
        orangeEyesRef.current.style.top = `${90 + orangePos.faceY}px`;
        const oo = calcPupilOffset(orangePupilLRef.current, a.mouseX, a.mouseY, 5);
        orangePupilLRef.current.style.transform = `translate(${oo.x}px, ${oo.y}px)`;
        orangePupilRRef.current.style.transform = `translate(${oo.x}px, ${oo.y}px)`;
      }
    }

    /* ---- Yellow ---- */
    if (charYellowRef.current) {
      if (isShowingPwd) {
        charYellowRef.current.style.transform = "skewX(0deg)";
      } else {
        charYellowRef.current.style.transform = `skewX(${yellowPos.bodySkew}deg)`;
      }
    }

    if (
      yellowEyesRef.current &&
      yellowPupilLRef.current &&
      yellowPupilRRef.current &&
      yellowMouthRef.current
    ) {
      if (a.isLoginError) {
        yellowEyesRef.current.style.left = "35px";
        yellowEyesRef.current.style.top = "45px";
        yellowPupilLRef.current.style.transform = "translate(-3px, 4px)";
        yellowPupilRRef.current.style.transform = "translate(-3px, 4px)";
        yellowMouthRef.current.style.left = "30px";
        yellowMouthRef.current.style.top = "92px";
        yellowMouthRef.current.style.transform = "rotate(-8deg)";
      } else if (isLookingAway) {
        yellowEyesRef.current.style.left = "20px";
        yellowEyesRef.current.style.top = "30px";
        yellowPupilLRef.current.style.transform = "translate(-5px, -5px)";
        yellowPupilRRef.current.style.transform = "translate(-5px, -5px)";
        yellowMouthRef.current.style.left = "15px";
        yellowMouthRef.current.style.top = "78px";
        yellowMouthRef.current.style.transform = "rotate(0deg)";
      } else if (isShowingPwd) {
        yellowEyesRef.current.style.left = "20px";
        yellowEyesRef.current.style.top = "35px";
        yellowPupilLRef.current.style.transform = "translate(-5px, -4px)";
        yellowPupilRRef.current.style.transform = "translate(-5px, -4px)";
        yellowMouthRef.current.style.left = "10px";
        yellowMouthRef.current.style.top = "88px";
        yellowMouthRef.current.style.transform = "rotate(0deg)";
      } else {
        yellowEyesRef.current.style.left = `${52 + yellowPos.faceX}px`;
        yellowEyesRef.current.style.top = `${40 + yellowPos.faceY}px`;
        const yo = calcPupilOffset(yellowPupilLRef.current, a.mouseX, a.mouseY, 5);
        yellowPupilLRef.current.style.transform = `translate(${yo.x}px, ${yo.y}px)`;
        yellowPupilRRef.current.style.transform = `translate(${yo.x}px, ${yo.y}px)`;
        yellowMouthRef.current.style.left = `${40 + yellowPos.faceX}px`;
        yellowMouthRef.current.style.top = `${88 + yellowPos.faceY}px`;
        yellowMouthRef.current.style.transform = "rotate(0deg)";
      }
    }
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Error animation                                                 */
  /* ---------------------------------------------------------------- */
  function triggerLoginError() {
    if (shakeTimerRef.current) clearTimeout(shakeTimerRef.current);
    if (errorRecoverTimerRef.current) clearTimeout(errorRecoverTimerRef.current);

    setShakeHead(false);
    setShowOrangeMouth(true);

    anim.current.isLoginError = true;
    anim.current.isPasswordFocused = false;
    updateCharacters();

    shakeTimerRef.current = setTimeout(() => {
      setShakeHead(true);
      shakeTimerRef.current = null;
    }, 350);

    errorRecoverTimerRef.current = setTimeout(() => {
      anim.current.isLoginError = false;
      errorRecoverTimerRef.current = null;
      setShowOrangeMouth(false);
      setShakeHead(false);
      updateCharacters();
    }, 2500);
  }

  /* ---------------------------------------------------------------- */
  /*  Effects                                                         */
  /* ---------------------------------------------------------------- */

  /* Mouse tracking */
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      anim.current.mouseX = e.clientX;
      anim.current.mouseY = e.clientY;
      if (!anim.current.isTyping && !anim.current.isLoginError) {
        updateCharacters();
      }
    };
    document.addEventListener("mousemove", handleMouseMove);
    return () => document.removeEventListener("mousemove", handleMouseMove);
  }, [updateCharacters]);

  /* Blinking */
  useEffect(() => {
    function scheduleBlinkPurple() {
      purpleBlinkTimerRef.current = setTimeout(() => {
        anim.current.isPurpleBlinking = true;
        updateCharacters();
        purpleBlinkTimerRef.current = setTimeout(() => {
          anim.current.isPurpleBlinking = false;
          updateCharacters();
          scheduleBlinkPurple();
        }, 150);
      }, Math.random() * 4000 + 3000);
    }

    function scheduleBlinkBlack() {
      blackBlinkTimerRef.current = setTimeout(() => {
        anim.current.isBlackBlinking = true;
        updateCharacters();
        blackBlinkTimerRef.current = setTimeout(() => {
          anim.current.isBlackBlinking = false;
          updateCharacters();
          scheduleBlinkBlack();
        }, 150);
      }, Math.random() * 4000 + 3000);
    }

    scheduleBlinkPurple();
    scheduleBlinkBlack();

    return () => {
      if (purpleBlinkTimerRef.current) clearTimeout(purpleBlinkTimerRef.current);
      if (blackBlinkTimerRef.current) clearTimeout(blackBlinkTimerRef.current);
    };
  }, [updateCharacters]);

  /* Cleanup all timers on unmount */
  useEffect(() => {
    return () => {
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      if (errorRecoverTimerRef.current) clearTimeout(errorRecoverTimerRef.current);
      if (shakeTimerRef.current) clearTimeout(shakeTimerRef.current);
      if (peekTimerRef.current) clearTimeout(peekTimerRef.current);
      if (purpleBlinkTimerRef.current) clearTimeout(purpleBlinkTimerRef.current);
      if (blackBlinkTimerRef.current) clearTimeout(blackBlinkTimerRef.current);
    };
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Handlers                                                        */
  /* ---------------------------------------------------------------- */

  function setTyping(typing: boolean) {
    anim.current.isTyping = typing;
    if (typing) {
      anim.current.isLookingAtEachOther = true;
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      typingTimerRef.current = setTimeout(() => {
        anim.current.isLookingAtEachOther = false;
        updateCharacters();
      }, 800);
    } else {
      anim.current.isLookingAtEachOther = false;
    }
    updateCharacters();
  }

  function schedulePeek() {
    const pwdLen = passwordInputRef.current?.value.length ?? 0;
    if (pwdLen > 0 && anim.current.showPassword) {
      peekTimerRef.current = setTimeout(() => {
        const pwdLen2 = passwordInputRef.current?.value.length ?? 0;
        if (pwdLen2 > 0 && anim.current.showPassword) {
          anim.current.isPurplePeeking = true;
          updateCharacters();
          peekTimerRef.current = setTimeout(() => {
            anim.current.isPurplePeeking = false;
            updateCharacters();
            schedulePeek();
          }, 800);
        }
      }, Math.random() * 3000 + 2000);
    }
  }

  function handleTogglePassword() {
    const next = !showPassword;
    setShowPassword(next);
    anim.current.showPassword = next;
    if (next) {
      schedulePeek();
    } else {
      if (peekTimerRef.current) clearTimeout(peekTimerRef.current);
      anim.current.isPurplePeeking = false;
      updateCharacters();
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const payload = await apiRequest<LoginResponse>(
        { baseUrl: serverUrl },
        "/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ username, password }),
        },
      );
      setAuth(payload);
      window.localStorage.setItem(LAST_USERNAME_KEY, username);
      if (rememberPassword) {
        window.localStorage.setItem(REMEMBER_PASSWORD_KEY, "true");
        window.localStorage.setItem(STORED_PASSWORD_KEY, encodePwd(password));
      } else {
        window.localStorage.removeItem(REMEMBER_PASSWORD_KEY);
        window.localStorage.removeItem(STORED_PASSWORD_KEY);
      }
      window.location.hash = "#/app";
    } catch (loginError) {
      if (loginError instanceof ApiError) {
        setError(loginError.message);
      } else {
        setError("无法连接到后端服务，请检查服务器地址。");
      }
      triggerLoginError();
    } finally {
      setIsLoading(false);
    }
  }

  /* ---------------------------------------------------------------- */
  /*  JSX                                                             */
  /* ---------------------------------------------------------------- */

  return (
    <div className="alp-page">
      {/* ---------- Left Panel (characters) ---------- */}
      <div className="alp-left" aria-hidden="true">
        <div className="alp-logo">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
            <path d="M12 2L15 9H9L12 2Z" />
            <path d="M12 22L9 15H15L12 22Z" />
            <path d="M2 12L9 9V15L2 12Z" />
            <path d="M22 12L15 15V9L22 12Z" />
          </svg>
          <span>{APP_NAME}</span>
        </div>

        <div className="alp-characters-wrapper">
          <div className="alp-characters-scene">
            {/* Purple */}
            <div className="alp-character alp-char-purple" ref={charPurpleRef}>
              <div
                className={`alp-eyes alp-purple-eyes ${shakeHead ? "shake-head" : ""}`}
                ref={purpleEyesRef}
              >
                <div className="alp-eyeball alp-purple-eye" ref={purpleEyeLRef}>
                  <div className="alp-pupil alp-purple-pupil" ref={purplePupilLRef} />
                </div>
                <div className="alp-eyeball alp-purple-eye" ref={purpleEyeRRef}>
                  <div className="alp-pupil alp-purple-pupil" ref={purplePupilRRef} />
                </div>
              </div>
            </div>

            {/* Black */}
            <div className="alp-character alp-char-black" ref={charBlackRef}>
              <div
                className={`alp-eyes alp-black-eyes ${shakeHead ? "shake-head" : ""}`}
                ref={blackEyesRef}
              >
                <div className="alp-eyeball alp-black-eye" ref={blackEyeLRef}>
                  <div className="alp-pupil alp-black-pupil" ref={blackPupilLRef} />
                </div>
                <div className="alp-eyeball alp-black-eye" ref={blackEyeRRef}>
                  <div className="alp-pupil alp-black-pupil" ref={blackPupilRRef} />
                </div>
              </div>
            </div>

            {/* Orange */}
            <div className="alp-character alp-char-orange" ref={charOrangeRef}>
              <div
                className={`alp-eyes alp-orange-eyes ${shakeHead ? "shake-head" : ""}`}
                ref={orangeEyesRef}
              >
                <div className="alp-bare-pupil" ref={orangePupilLRef} />
                <div className="alp-bare-pupil" ref={orangePupilRRef} />
              </div>
              <div
                className={`alp-orange-mouth alp-orange-mouth-init ${showOrangeMouth ? "visible" : ""} ${shakeHead ? "shake-head" : ""}`}
                ref={orangeMouthRef}
              />
            </div>

            {/* Yellow */}
            <div className="alp-character alp-char-yellow" ref={charYellowRef}>
              <div
                className={`alp-eyes alp-yellow-eyes ${shakeHead ? "shake-head" : ""}`}
                ref={yellowEyesRef}
              >
                <div className="alp-bare-pupil" ref={yellowPupilLRef} />
                <div className="alp-bare-pupil" ref={yellowPupilRRef} />
              </div>
              <div
                className={`alp-yellow-mouth alp-yellow-mouth-init ${shakeHead ? "shake-head" : ""}`}
                ref={yellowMouthRef}
              />
            </div>
          </div>
        </div>
      </div>

      {/* ---------- Right Panel (form) ---------- */}
      <div className="alp-right">
        <div className="alp-form-container">
          <div className="alp-sparkle">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L13.5 9H10.5L12 2Z" fill="#1a1a2e" />
              <path d="M12 22L10.5 15H13.5L12 22Z" fill="#1a1a2e" />
              <path d="M2 12L9 10.5V13.5L2 12Z" fill="#1a1a2e" />
              <path d="M22 12L15 13.5V10.5L22 12Z" fill="#1a1a2e" />
            </svg>
          </div>

          <div className="alp-form-header">
            <h1>欢迎回来</h1>
            <p>登录您的账号以继续</p>
          </div>

          <form className="alp-form" onSubmit={handleSubmit}>
            <div className="alp-form-group">
              <label htmlFor="username">账户</label>
              <div className="alp-input-wrap">
                <input
                  id="username"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  onFocus={() => setTyping(true)}
                  onBlur={() => setTyping(false)}
                  placeholder="请输入账户"
                  required
                />
              </div>
            </div>

            <div className="alp-form-group">
              <label htmlFor="password">密码</label>
              <div className="alp-input-wrap">
                <input
                  id="password"
                  ref={passwordInputRef}
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={() => {
                    anim.current.isPasswordFocused = true;
                    updateCharacters();
                  }}
                  onBlur={() => {
                    anim.current.isPasswordFocused = false;
                    updateCharacters();
                  }}
                  placeholder="请输入密码"
                  required
                />
                <button
                  type="button"
                  className="alp-toggle-password"
                  onClick={handleTogglePassword}
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <div className="alp-remember-row">
              <label className="alp-remember-label">
                <input
                  type="checkbox"
                  checked={rememberPassword}
                  onChange={(e) => setRememberPassword(e.target.checked)}
                />
                <span className="alp-remember-check" />
                <span>记住密码</span>
              </label>
            </div>

            {error ? (
              <div className="alp-error-msg">{error}</div>
            ) : null}

            <button
              type="submit"
              className="alp-btn-login"
              disabled={isLoading || !username || !password}
            >
              <span className="alp-btn-text">
                {isLoading ? "登录中…" : "登录"}
              </span>
              <div className="alp-btn-hover">
                <span>{isLoading ? "登录中…" : "登录"}</span>
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="5" y1="12" x2="19" y2="12" />
                  <polyline points="12 5 19 12 12 19" />
                </svg>
              </div>
            </button>
          </form>

          <div className="alp-form-footer">
            <button
              className="alp-back-link"
              onClick={() => {
                window.location.hash = "#/onboarding";
              }}
              type="button"
            >
              ← 返回环境检测
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
