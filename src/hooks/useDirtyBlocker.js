import { useEffect } from 'react';
import { useBlocker } from 'react-router-dom';

export function useDirtyBlocker(when, message = '저장하지 않은 변경사항이 있습니다. 페이지를 이동할까요?') {
  const blocker = useBlocker(({ currentLocation, nextLocation }) => when && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (blocker.state !== 'blocked') return;
    if (window.confirm(message)) blocker.proceed();
    else blocker.reset();
  }, [blocker, message]);
}
