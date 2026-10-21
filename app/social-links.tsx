import {Link2} from 'lucide-react';
import {socialPlatform, type SocialIconName, type SocialLinkRecord} from './social-platform';

function Glyph({name}: {name: SocialIconName}) {
  if (name === 'link') return <Link2 size={18} aria-hidden="true"/>;
  const common = {viewBox: '0 0 24 24', width: 18, height: 18, 'aria-hidden': true, fill: 'currentColor'} as const;
  if (name === 'facebook') return <svg {...common}><path d="M14.5 8.5V6.8c0-.7.5-1 1.2-1H17V3h-2.1C12.2 3 11 4.5 11 6.6v1.9H9v2.7h2V21h3.5v-9.8h2.3l.4-2.7h-2.7z"/></svg>;
  if (name === 'instagram') return <svg {...common}><path d="M8 3h8a5 5 0 0 1 5 5v8a5 5 0 0 1-5 5H8a5 5 0 0 1-5-5V8a5 5 0 0 1 5-5zm8 1.8H8A3.2 3.2 0 0 0 4.8 8v8A3.2 3.2 0 0 0 8 19.2h8a3.2 3.2 0 0 0 3.2-3.2V8A3.2 3.2 0 0 0 16 4.8zM12 8.2A3.8 3.8 0 1 1 8.2 12 3.8 3.8 0 0 1 12 8.2zm0 1.6A2.2 2.2 0 1 0 14.2 12 2.2 2.2 0 0 0 12 9.8zM17.4 6.4a1 1 0 1 1-1 1 1 1 0 0 1 1-1z"/></svg>;
  if (name === 'tiktok') return <svg {...common}><path d="M14 3h2.2a4.8 4.8 0 0 0 3.3 3.2v2.3a7 7 0 0 1-3.3-1v6.2a5.7 5.7 0 1 1-5.7-5.7c.3 0 .6 0 .9.1v2.5a3.2 3.2 0 1 0 2.2 3.1V3z"/></svg>;
  if (name === 'whatsapp') return <svg {...common}><path d="M12 3.2A8.6 8.6 0 0 0 5.2 16.7L4 21l4.4-1.2A8.6 8.6 0 1 0 12 3.2zm4.8 12.1c-.2.6-1.2 1.1-1.7 1.2s-1.3.2-2.1-.1-2.4-1-3.3-1.8-1.9-2.1-2.1-2.8.2-1.4.6-1.6.5-.3.7-.3h.5c.2 0 .4 0 .5.4s.6 1.5.7 1.6.1.3 0 .5-.2.4-.4.6-.3.4-.1.6.8 1.3 1.7 1.8 1.1.6 1.3.5.6-.2.8-.5.4-.6.6-.5.5.1 1.2.6 1.4.7.5.2.6.3.1.6-.1 1.2z"/></svg>;
  if (name === 'wechat') return <svg {...common}><path d="M9.2 4C6 4 3.4 6.2 3.4 9c0 1.6.9 3 2.3 4l-.5 1.9 2-.9c.6.2 1.3.3 2 .3.3 0 .6 0 .9-.1-.2-.5-.3-1-.3-1.5 0-2.6 2.4-4.7 5.4-4.7.2 0 .4 0 .6 0C15.2 5.6 12.4 4 9.2 4zm-2 3.2a.8.8 0 1 1 0 1.6.8.8 0 0 1 0-1.6zm4 0a.8.8 0 1 1 0 1.6.8.8 0 0 1 0-1.6zM16.2 9.2c-2.6 0-4.7 1.8-4.7 4s2.1 4 4.7 4c.5 0 1-.1 1.5-.2l1.7.8-.4-1.5c1.1-.8 1.8-1.9 1.8-3.1 0-2.2-2.1-4-4.6-4zm-1.6 2.5a.7.7 0 1 1 0 1.4.7.7 0 0 1 0-1.4zm3.2 0a.7.7 0 1 1 0 1.4.7.7 0 0 1 0-1.4z"/></svg>;
  if (name === 'telegram') return <svg {...common}><path d="M20.8 4.3 3.7 10.9c-1.2.5-1.2 1.1-.2 1.4l4.4 1.4 10.2-6.4c.5-.3.9-.1.6.2l-8.3 7.5-.3 4.5c.4 0 .6-.2.9-.4l2.1-2 4.4 3.2c.8.5 1.4.2 1.6-.7l2.9-13.6c.3-1.2-.4-1.7-1.2-1.3z"/></svg>;
  if (name === 'youtube') return <svg {...common}><path d="M21 8.2a3 3 0 0 0-2.1-2.1C17.2 5.7 12 5.7 12 5.7s-5.2 0-6.9.4A3 3 0 0 0 3 8.2 31 31 0 0 0 2.6 12a31 31 0 0 0 .4 3.8 3 3 0 0 0 2.1 2.1c1.7.4 6.9.4 6.9.4s5.2 0 6.9-.4a3 3 0 0 0 2.1-2.1 31 31 0 0 0 .4-3.8 31 31 0 0 0-.4-3.8zM10.4 15.1V8.9L15.2 12z"/></svg>;
  if (name === 'linkedin') return <svg {...common}><path d="M5.7 3.2A1.8 1.8 0 1 1 3.9 5a1.8 1.8 0 0 1 1.8-1.8zM4 8.2h3.4V21H4zM10 8.2h3.2v1.7h.1c.4-.8 1.5-1.8 3.2-1.8 3.4 0 4 2.2 4 5.1V21H17v-6.3c0-1.5 0-3.4-2.1-3.4s-2.4 1.6-2.4 3.3V21H10z"/></svg>;
  return <svg {...common}><path d="M4 4.5 10.2 12 4 19.5h2.2l4.8-5.8 4 5.8H20l-6.5-8.1L19.6 4.5h-2.2l-4.4 5.3-3.6-5.3z"/></svg>;
}

export function SocialIcon({name, url}: {name: string; url: string}) {
  return <span className={`social-icon ${socialPlatform(name, url)}`}><Glyph name={socialPlatform(name, url)}/></span>;
}

export function SocialLinkList({links, className}: {links: SocialLinkRecord[]; className?: string}) {
  if (!links.length) return null;
  return <ul className={className || 'social-link-list'}>
    {links.map(link => <li key={`${link.id}-${link.url}`}>
      <a href={link.url} target="_blank" rel="noopener noreferrer">
        <SocialIcon name={link.name} url={link.url}/>
        <span>{link.name}</span>
      </a>
    </li>)}
  </ul>;
}
